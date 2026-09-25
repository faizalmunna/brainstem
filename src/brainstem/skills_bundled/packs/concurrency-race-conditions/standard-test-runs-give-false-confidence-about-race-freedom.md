---
name: standard-test-runs-give-false-confidence-about-race-freedom
description: Diagnose why a fully green concurrent test suite still ships a race condition because ordinary test runs almost never hit the actual narrow interleaving window.
triggers: ["all tests pass but we still got a race condition in production", "how do i actually test for race conditions", "concurrent code has 100 percent coverage but still has bugs", "test suite green but race happened in prod", "how to reproduce a race in a unit test"]
permissions: ["READ"]
---

## Symptom
A concurrency bug reaches production (or is found by a user/incident)
despite the relevant code having unit or integration tests that
exercise it concurrently and pass reliably, sometimes for a long time.
Post-incident, someone runs the exact same test suite dozens of times and
it keeps passing, which raises the uncomfortable question of what the
tests were actually verifying -- the answer is usually that the tests
call the concurrent code from multiple threads but never with any
mechanism to force the specific interleaving that triggers the bug, so
they've been testing "runs without crashing most of the time" rather than
"is free of this race."

## Likely causes
1. **The test spins up N threads/tasks and joins them, but nothing forces
   the actual racy interleaving to occur** -- on modern hardware, two
   threads doing a small amount of work often just don't happen to
   overlap in the few-nanosecond window a race requires, especially when
   the operations are fast and the thread count is low relative to core
   count; the test *could* catch the bug, but only with extremely low
   probability per run, which is functionally the same as never for a
   fast CI suite run once per commit.
2. **The test asserts only on the final aggregate result, not on
   intermediate invariants** -- e.g. a test that runs 1000 concurrent
   increments and checks the final counter value will usually still pass
   even with an occasional lost update, because a small number of lost
   increments out of 1000 can be lucky enough not to trip a
   loosely-written assertion, or the assertion uses a range/tolerance
   instead of an exact expected value.
3. **Mocked dependencies remove the real timing variability that exposes
   the race** -- tests commonly mock I/O, database calls, or network
   requests to run fast and deterministically, but the real race depends
   on the variable latency of that I/O to create the window in the first
   place (e.g. a check-then-act race across a real network round-trip);
   an instant mock never creates that window at all.
4. **The test environment's low concurrency (few cores, few threads
   allotted in CI) makes the race probabilistically much rarer than in
   production**, compounding with the previous causes -- see also the
   single-core-CI class of this problem, which is a specific instance of
   this broader "tests don't actually exercise real concurrency" issue.

## Diagnose
- For any existing test that exercises concurrent code and passes, ask
  explicitly: does this test force the two (or more) racing operations to
  interleave at the exact point the bug requires, or does it merely run
  them "at the same time" and hope? Inspect for the presence (or absence)
  of any synchronization barrier, deterministic scheduling control, or
  injected delay designed to force the interleaving.
- Run the existing "concurrent" test hundreds or thousands of times in a
  loop (most test runners support a repeat-count flag) rather than once,
  and watch for a non-zero failure rate -- if it fails even 1 time in
  10,000, that's strong evidence the test technique is probabilistic
  rather than deterministic, and the same low-probability event is
  exactly what reaches production at scale.
- Where the language ecosystem provides a dedicated concurrency-testing
  tool, use it instead of ad hoc threads-plus-sleep: deterministic
  interleaving exploration/model checkers, thread-schedule fuzzers, or a
  race detector run continuously during the test (ThreadSanitizer for
  native code, equivalent tooling elsewhere) that flags unsynchronized
  access independent of whether the race actually manifested this run.
- Audit test assertions on concurrent operations for tolerance/looseness
  -- a test that accepts "counter is close to N" or only checks the
  suite didn't crash, rather than an exact expected value or an explicit
  structural invariant (no duplicates, no cycles, no negative balance),
  is a candidate for a false-confidence rewrite even if it never fails.

## Fix
Replace or supplement probability-dependent concurrent tests with
techniques that force or detect the race deterministically:
- Add explicit synchronization points (barriers, latches, or a
  coordination primitive) inside the test to force multiple threads to
  reach the racy code at the same instant, rather than relying on
  natural scheduling to occasionally align them -- e.g. have all threads
  wait on a start barrier so they enter the critical section
  simultaneously, maximizing contention instead of leaving it to chance.
- For check-then-act or ordering-dependent races, use dependency
  injection or test hooks to insert a controlled delay or pause at the
  exact point between the check and the act, and drive the interleaving
  from the test itself (thread 1 pauses there, thread 2 runs its
  conflicting operation, thread 1 resumes) -- this makes the race
  reproduce on every single run instead of occasionally.
- Run relevant tests under a race detector as a standing CI gate
  (ThreadSanitizer, or the ecosystem's equivalent) so unsynchronized
  access is flagged from static/dynamic instrumentation, independent of
  whether the specific interleaving happened to occur during that run --
  this catches races the probabilistic approach would miss entirely.
- Tighten assertions on concurrent test outcomes to exact expected values
  and explicit structural invariants rather than approximate or
  crash-only checks, and run each concurrency-sensitive test many times
  (tens to hundreds) as part of the standard suite rather than once,
  accepting the added CI time as the cost of actual coverage for this
  bug class.
- Where feasible, use real (not mocked) I/O with realistic latency
  variance for tests specifically targeting timing-dependent races, or
  inject artificial jitter into mocks used in concurrency tests so the
  window the race depends on can actually open.

## Pitfalls
- Adding `sleep()` calls to "make the test more reliable" without an
  explicit understanding of which specific interleaving the sleep is
  meant to force -- a sleep tuned to make a test reliably pass or fail
  on today's CI hardware is not portable to different hardware, load, or
  a future refactor, and tends to just move the flakiness rather than
  eliminate it.
- Treating a single successful stress-test run (even a large one) as
  proof of correctness and moving on -- probabilistic tests reduce risk
  but don't eliminate it the way a deterministic interleaving test or a
  race detector finding zero issues does; conflating "ran many times
  without failing" with "proven race-free" repeats the same
  overconfidence this skill is about.
- Running the new deterministic/forced-interleaving tests locally during
  development but not wiring them into CI as a required, repeated gate --
  a test that exists but isn't run on every change, or is run once
  instead of many times, still allows the same class of regression to
  slip back in silently.

## Verify
Confirm the newly-added deterministic or forced-interleaving test fails
reliably (100% of runs) against the original buggy code when checked out,
and passes reliably (100% of many repeated runs, not just once) against
the fixed code -- this pair of checks (fails before, passes after,
consistently) is the actual evidence the test exercises the race rather
than being another instance of probability-dependent false confidence.
Where a race detector is used, confirm it reports zero findings on the
affected code path across a CI run that actually exercises that path.
