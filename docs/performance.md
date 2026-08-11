# Local performance profiling

Performance instrumentation is developer-only. The public CLI is unchanged.
Set `LABELIMGPP_TRACE` to a local output directory to record `trace.json` and
`summary.json`; paths stored in trace arguments are hashed.

Generate and measure the deterministic workload on the fixed Linux machine:

```bash
python tools/performance/generate_workload.py /tmp/labelimgpp-workload
python tools/performance/profile_workload.py /tmp/labelimgpp-workload \
  --corpus yolo \
  --output profile-results/current
```

The profiler performs one warm-up and five measured runs, writing resource
CSV, Chrome-trace JSON, `cProfile` data/text, JSON summary, and a Markdown
comparison. It exits nonzero if any acceptance check fails. For a native
sampling flamegraph, install the `profile` extra and run:

```bash
python tools/performance/profile_with_flamegraph.py \
  /tmp/labelimgpp-workload --corpus yolo \
  --output profile-results/current
```

The wrapper writes `flamegraph.svg` alongside the other ignored local reports.
RSS acceptance is measured around five repeated filter/scroll/canvas cycles on
the already-populated widgets. The report also retains whole-profiler process
RSS growth separately, so allocator effects from rebuilding the benchmark
fixture remain visible without being confused with the application cycle gate.
Cold navigation uses the generated 4K/8K JPEG pack. The application reserves
96 MiB for its five-frame cache and 16 MiB for each gallery thumbnail cache,
keeping the combined cache ceiling at 128 MiB.

Workstation acceptance remains: input latency below 50 ms p95 with no
application pause over 100 ms; cold navigation below 500 ms p95 and prefetched
navigation below 100 ms p95; first image below one second and a complete 10k
list below two seconds; background progress within 250 ms and cancellation
within 500 ms; caches below 128 MiB with less than 10 percent steady-state RSS
growth.

## Smart-video gate

Generate only the optional deterministic media corpus, then run the dedicated
profiler:

```bash
python tools/performance/generate_workload.py /tmp/labelimgpp-video \
  --video-only --video-profile full
python tools/performance/profile_video.py /tmp/labelimgpp-video \
  --output profile-results/video-current
```

The corpus contains CFR MP4 and AVI, VFR MKV, long-GOP MP4, rotated MOV,
4K/8K navigation clips, a still image for document switching, and a textured
multi-frame tracking scene. A `smoke`
profile with reduced dimensions is available for tests. Media content is
generated with PyAV; when the `ffmpeg` executable is present it attaches a real
MOV display matrix for the rotation fixture.

The video profiler performs one warm-up and five measured repetitions. Each
repetition opens the video through the real `MainWindow`, scrubs through the
timeline, advances playback, paints the timeline and canvas, and commits a
drawn track while a Qt timer measures event-loop stalls. It also checks cold
seek below 500 ms p95, prefetched lookup below 100 ms p95, first-frame open
below one second, event-loop latency below 50 ms p95 with no pause over 100 ms,
progress within 250 ms, cancellation within 500 ms, the 128 MiB combined cache
ceiling, and less than 10 percent steady-state RSS growth across navigation,
tracking, image-switch, and atomic-export cycles. It writes `summary.json`,
`resources.csv`, cProfile output, and a Markdown comparison and exits nonzero
on a failed gate.
