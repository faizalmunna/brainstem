---
name: sampling-rate-misses-brief-hot-path
description: A sampling profiler shows a smooth, unremarkable profile even though a real short-lived spike is causing intermittent latency.
triggers: ["profiler doesn't show the spike I'm seeing in metrics", "sampling profiler missed the hot path", "cpu profile looks flat but latency spikes", "brief bottleneck not showing up in flame graph"]
permissions: ["READ"]
---

## Symptom

Latency metrics (or user reports) show clear, repeated spikes, but a
sampling CPU profiler run over the same period produces a flame graph
that looks flat and unremarkable -- no single frame stands out as
disproportionately hot, even though something is clearly costing time
intermittently.

## Likely causes

- **Sample rate too coarse relative to the event's duration.** A
  profiler sampling at, say, 100Hz (every 10ms) will statistically miss
  or barely register a hot path that only runs for 1-2ms, even if that
  hot path is the entire cause of an occasional latency spike -- the
  sampler simply isn't looking often enough to catch it.
- **The event is rare relative to the profiling window.** If the spike
  happens once every few seconds or less, and the profiling window is
  short, there may be zero samples landing inside the event purely by
  chance, independent of sample rate.
- **The cost isn't CPU time at all**, so a CPU-only sampling profiler
  structurally cannot see it -- e.g., a GC pause, a lock wait, a page
  fault, or a syscall blocking on I/O consumes wall-clock time without
  the thread being "on CPU" in a way the sampler attributes to a frame.
- **Sampling is per-thread or per-core in a way that misses cross-thread
  effects**, such as a spike caused by contention where the affected
  thread is idle/blocked (and so not sampled as "running") while a
  different thread holds a lock.

## Diagnose

1. Compare the spike's typical duration (from latency histograms or
   traces) against the profiler's sampling interval -- if the spike is
   shorter than roughly 5-10x the sampling interval, coarse sampling is
   a plausible cause of it being invisible, and a flat profile doesn't
   rule out a real hot path.
2. Re-run with a higher sample rate (or switch to an instrumentation-
   based/tracing profiler for a short, targeted window) specifically
   bracketing a known window when the spike is expected or reproducible.
3. Check whether the profiler being used only samples on-CPU time
   (common for many CPU profilers) versus off-CPU/wall-clock time (lock
   waits, I/O, scheduler delay) -- if the spike is I/O- or contention-
   driven, an on-CPU-only profiler will show nothing regardless of
   sample rate. Use an off-CPU profiler or a combined on/off-CPU flame
   graph.
4. Correlate spike timestamps with GC logs, syscall traces (e.g.,
   `strace -c` timing, or a language-level GC log) to rule out pause-
   based causes the CPU sampler can't see.
5. If the spike is rare, extend the profiling window or use an
   always-on continuous profiler so enough occurrences are captured to
   be statistically visible, rather than one short manual run.

## Fix

Match the profiling technique to the suspected event: for genuinely
brief CPU-bound hot paths, increase sample rate or switch to tracing/
instrumentation for a bounded investigation window; for anything
involving waiting (I/O, locks, GC, scheduler), use an off-CPU or wall-
clock profiler (or a combined view) instead of assuming a CPU sampler
will show it. When the event is rare, prefer longer-duration or
continuous profiling over repeated short manual snapshots, since a rare
event needs enough total observation time to accumulate samples.

## Pitfalls

Don't conclude "no bottleneck exists" from a flat CPU sampling profile
without first checking the sample rate against the event duration and
confirming the profiler even measures the right kind of time (on-CPU vs
wall-clock) -- a flat profile is evidence of absence only for the
specific thing that profiler mode measures. Also avoid cranking sample
rate up indefinitely as a blanket fix -- very high sample rates increase
profiling overhead and can itself distort timing for fast code (see the
profiling-overhead skill in this pack).

## Verify

After adjusting sampling rate or profiler type, reproduce the spike
under profiling and confirm a specific frame or off-CPU state now
appears in the flame graph with sample counts proportional to the
spike's known duration and frequency -- then correlate that finding
back against the original latency metric to confirm it explains the
magnitude of the observed spike, not just any hot-looking frame.
