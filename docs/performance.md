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
