---
name: wall-clock-profile-conflates-cpu-and-wait
description: A profiler flags a function as the slowest by wall-clock time, but the function is actually blocked waiting on I/O rather than doing expensive computation.
triggers: ["profiler says this function is slow but it's just waiting", "wall clock time high but CPU usage low", "optimized a function that was just blocked on I/O", "profile shows time spent in a function that calls a database"]
permissions: ["READ"]
---

## Symptom

A profile ranks a function very high by total wall-clock time spent "in"
it, so it gets treated as the optimization target. Optimizing its own
logic (tightening loops, caching intermediate values, algorithmic
improvements) does nothing, because almost all of that wall-clock time
was actually the thread blocked waiting on a network call, disk read, or
lock -- not executing any of the code that got optimized.

## Likely causes

- **The profiler measures wall-clock ("elapsed") time by default**,
  attributing all time between a function's entry and exit to that
  function, including time spent blocked inside a nested I/O call
  (database query, HTTP request, file read) -- the outer function looks
  expensive even though its own instructions execute in microseconds.
- **CPU-time and wall-time are not distinguished in the tool's default
  view.** Many profilers/APM tools show one aggregate "duration" number
  per span/frame without separately breaking out actual CPU-busy time
  versus time-on-a-wait-queue or blocked-on-syscall time.
- **The real cost is concurrency-related waiting** (waiting for a
  connection from a pool, waiting for a lock, waiting for a scheduler
  slot) which shows up as wall time inside whatever function happens to
  be waiting, misattributing a systemic resource contention problem to
  that one call site.
- **Self time vs. total time confusion** -- reading a flame graph's total
  (inclusive) time for a frame as if it were the frame's own (exclusive/
  self) cost, when most of that time actually belongs to a child call.

## Diagnose

1. Check whether the profiling tool reports CPU time separately from
   wall-clock time (many do, e.g., "on-CPU" vs "off-CPU" flame graphs,
   or a CPU% column next to duration) -- if the flagged function has high
   wall time but low CPU time, it's waiting, not computing.
   Sampling profilers that only ever sample while a thread is
   running/scheduled onto a CPU won't even show up-time for blocked
   code by default; confirm whether off-CPU sampling was enabled.
2. Look at the flame graph's leaf frames under the flagged function --
   if the bottom of the stack is a network/DB client call, syscall, or
   mutex/lock wait, the parent's wall time is dominated by that child,
   not its own logic.
3. Distinguish self time (exclusive) from total time (inclusive) for the
   frame in question; most profilers report both, and self time close to
   zero with high total time confirms the cost is downstream.
4. Correlate with infrastructure metrics for the suspected wait source
   at the same timestamp (DB query latency, connection pool wait time,
   lock wait counters) to confirm the waiting resource, not just infer it.

## Fix

Re-target the investigation at the actual wait source identified by
self-time/off-CPU analysis: if it's a database call, that's a query
performance or connection pool problem, not a code-logic problem in the
calling function; if it's a lock, that's a concurrency/contention
problem; if it's a downstream HTTP call, that's a network/dependency
latency problem. Optimize (or parallelize/cache/batch) at the point
where time is actually consumed, and use tracing (distributed traces or
async stack traces) rather than a single-process CPU profile when the
wait crosses a process or network boundary, since a local profiler
cannot see what the remote side is doing.

## Pitfalls

Don't "fix" a wall-time hotspot by wrapping the waiting call in a cache
or making it async without first confirming what it's actually waiting
on -- caching a slow query result papers over the query cost without
fixing it, and can introduce staleness bugs for a saving that a proper
index or query fix would have delivered without the tradeoff. Also
don't assume total (inclusive) time in a flame graph tells you where to
optimize -- always check self time first.

## Verify

After addressing the real wait source (e.g., adding a DB index,
increasing pool size, removing a lock), re-profile with CPU/wall-time
separated and confirm the previously flagged function's wall time has
dropped in proportion to the fix, and that its self time (which should
have been small all along) is unchanged, confirming the diagnosis was
correct rather than coincidental.
