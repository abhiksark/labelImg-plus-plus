"""Opt-in local tracing with zero instrumentation work in normal runs.

Set ``LABELIMGPP_TRACE`` to a directory before starting the application.  No
public CLI flag is added and no data leaves the machine.  Recorded filesystem
paths are represented by stable hashes in trace events.
"""

from contextlib import contextmanager
import atexit
import hashlib
import json
import os
import platform
import sys
import threading
import time


TRACE_DIRECTORY_ENV = 'LABELIMGPP_TRACE'


def hash_path(path):
    if path is None:
        return None
    normalized = os.path.normcase(os.path.abspath(os.fspath(path)))
    return hashlib.sha256(normalized.encode(
        'utf-8', errors='surrogateescape')).hexdigest()[:16]


class TraceRecorder:
    def __init__(self, output_dir):
        self.output_dir = os.path.abspath(os.fspath(output_dir))
        self._started_ns = time.perf_counter_ns()
        self._events = []
        self._lock = threading.Lock()
        self._closed = False

    @contextmanager
    def span(self, name, category='app', args=None):
        started = time.perf_counter_ns()
        try:
            yield
        finally:
            ended = time.perf_counter_ns()
            event = {
                'name': name,
                'cat': category,
                'ph': 'X',
                'ts': (started - self._started_ns) / 1000,
                'dur': (ended - started) / 1000,
                'pid': os.getpid(),
                'tid': threading.get_ident(),
                'args': dict(args or {}),
            }
            with self._lock:
                self._events.append(event)

    def instant(self, name, category='app', args=None):
        now = time.perf_counter_ns()
        with self._lock:
            self._events.append({
                'name': name,
                'cat': category,
                'ph': 'i',
                's': 't',
                'ts': (now - self._started_ns) / 1000,
                'pid': os.getpid(),
                'tid': threading.get_ident(),
                'args': dict(args or {}),
            })

    def complete(self, name, started_ns, category='app', args=None):
        """Record a duration whose work could not conveniently use ``with``."""
        ended = time.perf_counter_ns()
        event = {
            'name': name,
            'cat': category,
            'ph': 'X',
            'ts': (started_ns - self._started_ns) / 1000,
            'dur': (ended - started_ns) / 1000,
            'pid': os.getpid(),
            'tid': threading.get_ident(),
            'args': dict(args or {}),
        }
        with self._lock:
            self._events.append(event)

    def close(self):
        if self._closed:
            return
        self._closed = True
        os.makedirs(self.output_dir, exist_ok=True)
        with self._lock:
            events = list(self._events)
        trace_path = os.path.join(self.output_dir, 'trace.json')
        with open(trace_path, 'w', encoding='utf-8') as output:
            json.dump({'traceEvents': events}, output, separators=(',', ':'))

        durations = {}
        for event in events:
            if event.get('ph') == 'X':
                durations.setdefault(event['name'], []).append(event['dur'])
        operations = {}
        for name, values in durations.items():
            ordered = sorted(values)
            p95_index = max(0, int(len(ordered) * 0.95) - 1)
            operations[name] = {
                'count': len(values),
                'median_ms': ordered[len(ordered) // 2] / 1000,
                'p95_ms': ordered[p95_index] / 1000,
                'max_ms': ordered[-1] / 1000,
            }
        summary = {
            'python': sys.version.split()[0],
            'platform': platform.platform(),
            'logical_cpus': os.cpu_count(),
            'events': len(events),
            'operations': operations,
        }
        with open(os.path.join(self.output_dir, 'summary.json'), 'w',
                  encoding='utf-8') as output:
            json.dump(summary, output, indent=2, sort_keys=True)


_output_dir = os.environ.get(TRACE_DIRECTORY_ENV)
recorder = TraceRecorder(_output_dir) if _output_dir else None
if recorder is not None:
    atexit.register(recorder.close)


if recorder is None:
    def trace_span(_name, category='app', args=None):
        # Returning a shared-style no-op context manager avoids timers, locks,
        # path hashing, and event allocation in normal application runs.
        return _null_span()

    @contextmanager
    def _null_span():
        yield
else:
    def trace_span(name, category='app', args=None):
        return recorder.span(name, category=category, args=args)


def trace_instant(name, category='app', args=None):
    if recorder is not None:
        recorder.instant(name, category=category, args=args)
