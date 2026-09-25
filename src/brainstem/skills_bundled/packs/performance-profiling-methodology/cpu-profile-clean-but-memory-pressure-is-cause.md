---
name: cpu-profile-clean-but-memory-pressure-is-cause
description: CPU profiling shows no clear hotspot even though the application periodically stalls, and the real cause is garbage collection or allocation pressure.
triggers: ["CPU profile looks fine but app still pauses", "gc pauses causing latency spikes", "high memory allocation slowing things down", "cpu usage normal but throughput drops periodically"]
permissions: ["READ"]
---

## Symptom

The application shows periodic latency spikes, stutters, or throughput
dips, but a CPU profile taken during normal operation shows a
reasonably flat, unremarkable distribution of time across functions --
nothing looks like an obvious algorithmic hotspot, yet the stalls are
real and reproducible.

## Likely causes

- **Garbage collection pauses (stop-the-world or concurrent-mark
  pauses)** consume wall-clock time without being attributable to any
  single application function in a CPU profile -- the GC runs as part of
  the runtime, not as "your code," so standard CPU profiling of
  application frames doesn't surface it unless the tool specifically
  breaks out GC time.
- **High allocation rate creates GC pressure indirectly** -- code that
  allocates excessively (e.g., creating many short-lived objects in a
  hot loop, unnecessary boxing, string concatenation in a loop) doesn't
  look expensive per-instruction in a CPU profile, but it drives GC
  frequency and pause duration up, and the actual pause time shows up
  attributed to the GC subsystem or as generic "stopped" time, not to
  the allocating code.
- **Memory bandwidth/cache-miss effects** from poor data locality
  (scattered heap objects, pointer-chasing structures) slow down memory-
  bound code in a way that a CPU-instruction-count-oriented profile
  under-represents, since the CPU appears "busy" while actually stalled
  waiting on memory.
- **Swapping/paging under memory pressure** (the process's working set
  exceeds available RAM) causes OS-level stalls that are invisible to an
  application-level CPU profiler entirely, since the delay happens
  outside the process.

## Diagnose

1. Correlate the timing of latency spikes against GC logs (enable
   verbose/GC-logging for the runtime in use) -- a tight correlation
   between spike timestamps and GC pause events points directly at GC,
   independent of what the CPU profile shows.
2. Use a memory/allocation profiler (distinct from a CPU profiler --
   e.g., an allocation sampling tool, heap profiler, or object
   allocation tracker for the runtime in use) to find which code paths
   are allocating at the highest rate, since a CPU profiler generally
   will not rank code by allocation volume.
3. Check runtime-level GC metrics (pause count, pause duration
   distribution, heap size before/after collection, collection
   frequency) exposed by most managed runtimes -- rising pause frequency
   or duration over time suggests growing allocation pressure or heap
   fragmentation.
4. Check OS-level memory metrics (resident set size trend, page fault
   rate, swap activity) to rule out paging as a contributor outside the
   runtime's own GC.
5. If available, use a profiler mode that shows both on-CPU and GC/
   runtime-pause time on the same timeline, so the two are directly
   comparable rather than inferred from separate tools.

## Fix

Once allocation hot paths are identified, reduce allocation rate at the
source: reuse buffers/objects instead of allocating per-iteration or
per-request, prefer value types or pooling where the runtime supports
it, avoid unnecessary intermediate collections (e.g., chained
transformations that each allocate a new collection), and batch or
stream large data instead of materializing it all at once. Where GC
tuning is available (generation sizing, collector algorithm choice,
heap size), treat it as a complement to reducing allocation, not a
substitute -- tuning the collector around a high allocation rate usually
buys a smaller win than fixing the allocation pattern itself.

## Pitfalls

Don't chase GC tuning flags as the first move before establishing that
allocation pressure (not something else, like lock contention or I/O)
is actually the cause of the observed pauses -- GC tuning has a large
and confusing parameter space and can make pause behavior worse if
applied without diagnosis. Also don't assume "CPU profile is flat" means
"nothing to optimize" -- a flat CPU profile with an active memory
problem is exactly the signature this skill describes, and moving on
without checking allocation/GC metrics leaves the real cause unaddressed.

## Verify

After reducing allocation in the identified hot paths, compare GC pause
frequency and duration (from the same GC logging used to diagnose)
before and after, and confirm the application-level latency spikes that
motivated the investigation are reduced or eliminated in a load test or
production canary over a comparable traffic window.
