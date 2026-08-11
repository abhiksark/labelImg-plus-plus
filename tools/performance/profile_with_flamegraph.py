#!/usr/bin/env python3
"""Run the five-repetition profiler under py-spy and emit an SVG flamegraph."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('workload')
    parser.add_argument('--corpus', default='yolo')
    parser.add_argument('--output', default='profile-results')
    args = parser.parse_args()
    py_spy = shutil.which('py-spy')
    if py_spy is None:
        raise SystemExit(
            'py-spy is not installed; install the project profile extra')
    output = os.path.abspath(args.output)
    os.makedirs(output, exist_ok=True)
    profiler = os.path.join(
        os.path.dirname(__file__), 'profile_workload.py')
    flamegraph = os.path.join(output, 'flamegraph.svg')
    summary = os.path.join(output, 'summary.json')
    command = [
        py_spy, 'record', '--format', 'flamegraph',
        '--output', flamegraph,
        '--', sys.executable, profiler, os.path.abspath(args.workload),
        '--corpus', args.corpus, '--output', output,
    ]
    started_ns = time.time_ns()
    exit_code = subprocess.call(command)
    # py-spy 0.4.2 can report ECHILD after successfully collecting a short
    # child process. Accept only fresh, nonempty artifacts whose measured
    # profiler run itself passed; genuine launch/sampling failures still fail.
    try:
        if (os.path.getmtime(flamegraph) * 1_000_000_000 >= started_ns
                and os.path.getsize(flamegraph) > 0
                and os.path.getmtime(summary) * 1_000_000_000 >= started_ns):
            with open(summary, 'r') as stream:
                if json.load(stream).get('passed'):
                    return 0
    except (OSError, ValueError):
        pass
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
