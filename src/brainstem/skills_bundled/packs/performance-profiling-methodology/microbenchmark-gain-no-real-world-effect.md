---
name: microbenchmark-gain-no-real-world-effect
description: A microbenchmark shows a large speedup for an isolated function, but production latency under realistic load does not improve at all.
triggers: ["benchmark got 5x faster but production is the same", "microbenchmark improved but real latency didn't change", "isolated benchmark doesn't match production behavior", "optimization works in the benchmark but not in the app"]
permissions: ["READ"]
---

## Symptom

A targeted microbenchmark for a specific function or code path shows a
dramatic improvement (2x, 5x, 10x) after an optimization. The team ships
it expecting a visible win, but production latency, throughput, or
resource usage under real load shows no measurable change.

## Likely causes

- **The benchmarked code path isn't the critical path under real
  load.** A microbenchmark isolates one function and measures it in a
  tight loop, which says nothing about what fraction of a real request's
  total time that function occupies, or whether it even runs on the
  path that determines end-to-end latency (see the "optimized based on
  intuition" pattern for the same root issue from a different entry
  point).
- **The microbenchmark's conditions don't match production concurrency.**
  A single-threaded, uncontended microbenchmark can't reveal that the
  "optimized" code was never the limiting factor once dozens of
  concurrent requests are competing for a shared resource (a connection
  pool, a lock, a thread pool) -- the real bottleneck is contention, not
  the algorithm.
  the algorithm.
- **JIT/warmup and caching effects inflate the benchmark.** Tight
  microbenchmark loops let JIT compilers, CPU caches, and branch
  predictors reach a steady state that a single real request, running
  cold amid other unrelated work, never reaches -- the benchmark measures
  a best-case that production rarely hits.
- **The optimization traded one resource for another** (e.g., less CPU
  for more memory allocation, or lower latency for higher lock hold
  time) in a way the isolated benchmark doesn't capture, and the traded
  resource turns out to be the actual production constraint.

## Diagnose

1. Before trusting the microbenchmark result, check what percentage of
   real end-to-end request time the benchmarked function occupies in a
   production trace -- if it's small, a large isolated speedup was
   mathematically unlikely to move end-to-end latency regardless of how
   the benchmark went.
2. Run a load test (not a single-threaded microbenchmark) that exercises
   the optimized path under realistic concurrent request volume and
   compare end-to-end percentiles before/after, not just the isolated
   function's timing.
3. Check whether the microbenchmark included realistic warmup/cold-start
   conditions matching production request patterns, or whether it
   measured a hot, cache-friendly steady state that real traffic
   doesn't sustain.
4. Profile production (or a production-representative load test) after
   deploy to confirm the optimized function's share of total time
   actually shrank as expected, and check whether any other resource
   (memory, GC pressure, lock hold time) increased as a side effect.

## Fix

Treat microbenchmark results as necessary but not sufficient: use them
to confirm an optimization does what it claims to the specific code
path, but require a load test or production canary comparison of
end-to-end metrics before counting the work as done. Prioritize
optimization targets by their measured share of end-to-end time under
realistic concurrency, not by how much an isolated benchmark can be
made to improve.

## Pitfalls

Don't let an impressive isolated benchmark number substitute for an
end-to-end measurement in a status update or a PR description -- "5x
faster" is only meaningful with the denominator (5x faster relative to
what share of total time). Also watch for microbenchmark harnesses that
inadvertently let the compiler dead-code-eliminate the very work being
measured, producing a speedup number that reflects removed work rather
than a real optimization -- verify the benchmark still does the same
functional work by checking its output, not just its timing.

## Verify

Run the same benchmark methodology used originally to justify the
change, but also run a load test against a staging or canary
environment reproducing production concurrency and traffic mix, and
confirm the target production metric (endpoint p95, throughput) moves
by an amount consistent with the function's known share of end-to-end
time -- not just that the isolated benchmark number improved.
