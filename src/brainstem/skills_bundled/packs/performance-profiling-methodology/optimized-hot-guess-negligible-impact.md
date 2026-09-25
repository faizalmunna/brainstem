---
name: optimized-hot-guess-negligible-impact
description: An engineer spends days optimizing a function they were sure was slow, ships it, and end-to-end latency does not move at all.
triggers: ["I optimized this but it made no difference", "sped up the function but the request is still slow", "rewrote the slow part and nothing changed", "optimization had no effect on latency"]
permissions: ["READ"]
---

## Symptom

Someone identifies a piece of code that "feels" slow -- a nested loop, a
recursive function, a serialization step -- spends real time (hours to
days) rewriting it to be algorithmically better or micro-optimized, ships
it, and the metric that was supposed to improve (page load, request p95,
job runtime) is statistically indistinguishable from before. The code is
objectively faster in isolation; the system is not.

## Likely causes

- **The optimized code was never the bottleneck.** Intuition about "what
  should be slow" is usually built from CPU-bound reasoning (loops,
  algorithmic complexity) while the actual critical path is dominated by
  I/O wait, network round trips, or a downstream service call that
  dwarfs the CPU time being shaved.
- **The optimized code runs off the critical path or in parallel with
  something slower.** If the function runs concurrently with a slower
  operation (e.g., inside a `Promise.all`/async gather, or overlapped
  with I/O), shaving its wall time doesn't shorten the overall
  request because the slower sibling was already the limiting factor.
- **The optimization target was chosen from a microbenchmark or isolated
  profile, not from a production-representative trace of the actual
  request path**, so the "hot" function measured in isolation is cold in
  the context that matters.
- **The absolute time saved is real but tiny relative to total latency**
  -- turning a 2ms function into 0.2ms saves 1.8ms against a 400ms
  end-to-end request, which is invisible in aggregate percentiles and
  noise.

## Diagnose

1. Before touching code, capture an end-to-end trace or profile of a
   representative real request (not a synthetic call to just the
   suspect function) and read off what fraction of total wall time the
   suspect function actually occupies.
2. If it's under roughly 5-10% of total request time, treat it as a low
   priority regardless of how "obviously slow" it looks in isolation --
   even a 100% speedup there caps the possible end-to-end improvement at
   that same 5-10%.
3. Check whether the function runs concurrently with other work (async/
   parallel branches, overlapped I/O). If so, compute the *critical
   path* (the longest chain of dependent operations), not just the sum
   of each operation's own time -- a function can be "slow" in isolation
   but free on the critical path.
4. After the fact, compare before/after production percentiles (p50/p95/
   p99) for the specific endpoint over a matched time window and traffic
   volume, not just a local benchmark of the changed function.

## Fix

Establish a rule: no optimization work starts without first profiling
the actual end-to-end path under realistic conditions and confirming the
target function's share of total time is large enough that improving it
can plausibly move the metric being tracked. Rank candidate
optimizations by (percentage of end-to-end time) x (expected percentage
speedup), not by gut feeling about algorithmic elegance. When a function
sits off the critical path, the fix is often not to speed it up but to
confirm it's already overlapped correctly, or to shorten the critical
path elsewhere.

## Pitfalls

Don't justify a completed optimization retroactively by pointing at the
microbenchmark improvement alone ("it's 10x faster now") when the
question was always about end-to-end impact -- a 10x speedup on a
function that was 2% of total time is still only a ~1.8% end-to-end
gain at best, and often less once contention and scheduling noise are
accounted for. Also don't skip the end-to-end trace step because the
suspect code "obviously" looks like the bottleneck from reading it --
that's the exact intuition this failure mode exists to correct.

## Verify

Compare the same production percentile metric (e.g., p95 latency for the
affected endpoint) over an equivalent traffic window before and after
the change, with statistical significance considered (not just eyeballing
a dashboard), and confirm the improvement is at least in the ballpark
predicted by the function's measured share of end-to-end time.
