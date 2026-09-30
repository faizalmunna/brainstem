---
name: profiler-overhead-distorts-fast-code
description: Enabling an instrumentation-based profiler makes a fast function look disproportionately slow, or changes the relative ranking of hot spots entirely.
triggers: ["profiler shows a function as slow that isn't slow without profiling", "instrumentation profiler changed the results", "code is faster when I'm not profiling it", "heisenbug performance profiling overhead"]
permissions: ["READ"]
---

## Symptom

Running a profiler against a fast, frequently-called function (a
getter, a small utility, a hot inner-loop call) makes it appear as a
major cost center, but disabling the profiler and measuring wall-clock
time normally shows no such cost -- the act of measuring changed the
thing being measured, sometimes badly enough to invert which function
looks "hottest."

## Likely causes

- **Instrumentation-based profiling adds fixed per-call overhead**
  (entering/exiting a probe, recording a timestamp, incrementing a
  counter) that is roughly constant regardless of the function's actual
  work -- for a function that itself takes nanoseconds to microseconds,
  that fixed overhead can be a large multiple of the real cost, inflating
  it disproportionately relative to genuinely expensive functions.
- **Very frequently called small functions are hit hardest**, because
  the overhead is paid per invocation -- a function called a million
  times pays a million times the per-call instrumentation tax, which can
  dwarf functions called rarely but doing more real work each time,
  flipping the apparent ranking.
- **Sampling profilers are used at too high a frequency**, effectively
  behaving like instrumentation (interrupting execution very often),
  which introduces the same class of distortion even though sampling
  profilers are normally considered lower-overhead.
- **The profiler disables JIT optimizations or inlining while active**
  (common in some managed-runtime profilers), making code measurably
  slower under profiling for reasons unrelated to the profiler's own
  bookkeeping cost, purely because the runtime behaves differently when
  observed.

## Diagnose

1. Compare wall-clock timing of the full operation with the profiler
   attached versus detached (e.g., simple `time`-based measurement
   around the same code path) -- a large discrepancy (profiler-attached
   run is substantially slower overall) confirms measurement-induced
   distortion, not just distortion of one function's ranking.
2. Check the call count of the suspect function from the profiler's own
   output -- if it's extremely high (millions of calls) and each call
   does little work, suspect per-call instrumentation overhead before
   suspecting the function's logic.
3. Re-run with a statistical sampling profiler at a moderate rate
   instead of an instrumentation/tracing profiler, and see if the
   suspect function's relative ranking changes -- sampling profilers
   generally have much lower per-call overhead since they don't
   instrument every call site.
4. Check the specific profiler's documentation for known overhead
   characteristics and whether it disables inlining/JIT optimizations
   while attached (common for CPU/line-level profilers in JIT-compiled
   languages).

## Fix

For hot, frequently-called, individually-cheap functions, prefer
low-overhead statistical sampling profilers over instrumentation-based
ones, since sampling doesn't pay a per-call tax and more accurately
reflects real, unobserved behavior. When instrumentation-level detail is
genuinely needed (e.g., to see argument values or call chains), scope it
narrowly -- profile only the specific suspect region behind a flag or in
a short, targeted run -- rather than instrumenting the entire call graph
including unrelated hot loops. Cross-check any instrumentation-derived
finding against a normal, unprofiled wall-clock measurement before
acting on it.

## Pitfalls

Don't "optimize away" a function purely because an instrumentation
profiler ranked it high without checking its call count and per-call
cost against the overhead characteristics of that specific profiler --
this is a well-known way to spend effort removing or restructuring
correct, genuinely cheap code for no real-world benefit. Also don't
assume all sampling profilers are automatically overhead-free; very high
sample rates on a sampling profiler can reintroduce the same problem
(see the brief-hot-path skill in this pack for the opposite failure at
low sample rates).

## Verify

After forming a hypothesis from a profiler, confirm it against an
unprofiled (or minimally-profiled) wall-clock measurement of the same
operation -- the suspect function's contribution to total time should be
plausible without the profiler attached, not an artifact that
disappears the moment instrumentation is removed.
