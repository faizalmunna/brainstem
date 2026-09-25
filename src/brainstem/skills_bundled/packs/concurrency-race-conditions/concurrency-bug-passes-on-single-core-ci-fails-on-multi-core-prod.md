---
name: concurrency-bug-passes-on-single-core-ci-fails-on-multi-core-prod
description: Diagnose a concurrency bug that consistently passes in CI but fails intermittently in production because CI runs on fewer cores or a different scheduler than production hardware.
triggers: ["passes in ci but fails in production", "works on my laptop fails on the server", "flaky test only fails on the build farm", "bug only shows up on multi core machines", "cant reproduce on single core"]
permissions: ["READ"]
---

## Symptom
A concurrency-related bug (a race condition, an ordering assumption, a
missing synchronization primitive) never reproduces in the team's usual
environment -- a small CI runner, a single-core container, a developer
laptop with light load -- but reproduces reliably or semi-reliably on
production hardware with more cores, higher thread counts, or under real
concurrent traffic. Test suites are green, the code review found nothing
wrong by inspection, and the bug is often initially dismissed as
"environment flakiness" or blamed on infrastructure rather than the code,
because the exact same binary/build behaves differently depending only on
where it runs.

## Likely causes
1. **Genuine concurrency bug that requires actual parallel execution to
   manifest** -- on a single core, an OS scheduler running cooperative
   green threads, or a runtime with a global interpreter lock serializing
   bytecode execution, two logical threads may never truly execute
   simultaneously at the machine-instruction level, so a race that
   requires two real, concurrent memory accesses (a lost update, a
   visibility bug, a lock-free algorithm's ABA-style issue) simply cannot
   occur no matter how the code is scheduled -- it's not that CI got
   lucky, it's that the precondition for the race literally isn't met.
2. **Missing memory barriers that only matter under weaker hardware memory
   ordering** -- code that "happens to work" relies on assumptions valid
   on one CPU architecture's default ordering (e.g. x86's relatively
   strong ordering) but breaks on hardware with weaker default ordering
   (many ARM/RISC-V configurations) where a write can become visible to
   another core's read out of the order the source code implies, and CI
   runners and production may simply run on different CPU architectures
   or virtualization layers.
3. **Thread/worker count differs enough between environments to change the
   probability of a specific interleaving** -- CI containers are often
   capped at 1-2 vCPUs while production runs on machines with far more
   cores, so a thread pool sized relative to core count creates
   drastically different actual concurrency levels, and a race requiring
   3+ threads interleaved a specific way may have near-zero probability
   at 2 threads but a real, if still low, probability at 32.
4. **CI's test execution introduces incidental synchronization that
   production traffic doesn't** -- test frameworks often run steps in
   fixed sequence with implicit waits, mocked I/O that returns instantly
   and predictably (versus production's variable-latency real I/O and
   network jitter), or logging/instrumentation overhead that widens or
   removes the exact timing window the race depends on, making the test
   environment accidentally race-free by construction rather than by the
   code being correct.

## Diagnose
- Confirm the core count and scheduling model of both environments
  explicitly (`nproc`/container CPU limits in CI vs. production host or
  pod specs) rather than assuming they match -- this single check often
  immediately explains the discrepancy.
- Reproduce locally by constraining to the CI-like environment first (cap
  the process to 1-2 cores with the OS's CPU affinity or container CPU
  limit controls) and confirm the bug does *not* reproduce there, then
  progressively raise the core/thread count until it does -- this
  directly demonstrates the core-count dependency rather than assuming
  it.
- Check the CPU architecture of both environments (`uname -m`, or the
  cloud instance type) -- if CI runs on one architecture and production on
  another (e.g. x86 CI runners building for an ARM production fleet, or
  a local Apple Silicon dev machine versus x86 production), treat memory
  ordering differences as a live suspect, not an edge case.
- Run the suspect code under a race detector that instruments memory
  accesses directly rather than relying on the race actually manifesting
  as observable corruption (ThreadSanitizer, similar tools for other
  ecosystems) -- these tools can find the unsynchronized access even on a
  single-core CI machine, because they detect the absence of a
  happens-before relationship in the code, independent of whether the
  scheduler actually interleaves the threads that run.
- Add a deliberate artificial delay or force a specific interleaving via
  the language's concurrency-testing utilities (thread-interleaving
  test harnesses, deterministic scheduler simulation tools where the
  ecosystem provides one) to make the race reproduce on demand regardless
  of core count, turning a hardware-dependent flake into a deterministic
  test failure.

## Fix
Treat "it doesn't reproduce in CI" as inconclusive rather than as evidence
of correctness, and fix the underlying synchronization gap the same way
regardless of which environment exposed it:
- Add the correct synchronization primitive for the actual data being
  shared (a lock, an atomic operation, a proper memory-ordering
  annotation) rather than any fix that merely changes timing -- the goal
  is to make the code correct under the language's memory model on any
  number of cores and any architecture, not to make it pass on the
  specific hardware that happened to expose it.
- Where the bug traces to weak memory ordering assumptions, use the
  language's explicit ordering primitives (acquire/release semantics on
  atomics, documented memory barriers) rather than relying on a
  particular CPU architecture's stronger-than-required default behavior,
  so the code is portable across architectures instead of "correct on
  x86 only."
- Update CI to actually exercise realistic concurrency instead of masking
  the gap: run the relevant test suite on multi-core runners, and
  consider running a subset of concurrency-sensitive tests under a race
  detector as a required CI gate rather than only locally and
  occasionally.
- Where feasible, add the artificial-interleaving or forced-scheduling
  test harness used during diagnosis as a permanent regression test, so
  the specific race is caught deterministically in CI going forward
  rather than depending on CI's hardware happening to match production's.

## Pitfalls
- "Fixing" the CI environment to match production's core count and
  declaring victory once the test fails there too -- this makes the bug
  reproducible for diagnosis, but matching hardware is not the fix; the
  actual missing synchronization in the code still needs to be added.
  Matching environments closes the observability gap, not the bug.
- Adding a sleep/delay in the code to "give the other thread time to
  finish" after seeing it fix the symptom under test -- this reduces the
  probability of hitting the window without eliminating it, and the
  specific delay that "works" on today's CI hardware and load level is
  not guaranteed to be sufficient on tomorrow's production hardware or
  under higher load.
- Assuming a race detector finding "no issues" on a single-core run is a
  clean bill of health for concurrency correctness -- most race detectors
  report unsynchronized *access patterns* independent of actual
  interleaving and don't require the race to manifest, but code paths
  never exercised by the test run at all still won't be checked, so
  detector coverage is only as good as the test suite driving it.

## Verify
Confirm the fix by running the forced-interleaving or artificial-delay
reproduction from the diagnose step and verifying it no longer triggers
the bug across many repeated runs, not just the original CI environment.
Additionally run the race detector (ThreadSanitizer or equivalent) over
the fixed code under the same exercised code paths and confirm it reports
zero unsynchronized accesses on the affected memory, and add a CI job
that runs on a multi-core runner (or with CPU affinity explicitly
widened) so future regressions in this area have a real chance of being
caught before reaching production hardware.
