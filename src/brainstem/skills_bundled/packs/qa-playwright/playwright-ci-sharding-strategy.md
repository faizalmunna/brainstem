---
name: playwright-ci-sharding-strategy
description: Parallelize and shard a Playwright suite in CI to cut wall-clock time without introducing cross-test interference or unbalanced shard runtimes.
triggers: ["playwright tests slow in ci", "shard playwright tests", "parallelize e2e tests ci", "ci pipeline too slow tests", "unbalanced test shards"]
permissions: ["READ"]
---

## Symptom
The E2E suite takes long enough in CI to slow down the deploy/PR feedback
loop meaningfully, and/or after adding sharding, some shards finish in a
fraction of the time others take, or tests that passed individually start
failing only when run in parallel.

## Likely causes
1. **No sharding/parallelism configured at all**, running the full suite
   serially in CI even though Playwright supports both in-process
   parallel workers and cross-machine sharding.
2. **Naive/alphabetical sharding** that happens to group several slow
   tests into one shard and many fast tests into another, so total wall
   time is bounded by the slowest shard, not the average.
3. **Shared external state** (a shared test database, a shared account,
   a shared file on disk) that multiple parallel tests read/write
   concurrently, causing failures that only appear under parallel
   execution -- distinct from the same bug appearing in
   `playwright-flaky-test-diagnosis`, but frequently the same underlying
   root cause (test isolation).
4. **Fixed resource limits** (a rate-limited test API key, a connection
   pool sized for serial usage) that a sharded/parallel run exceeds, even
   though each individual test is correct on its own.

## Diagnose
- Check current CI configuration for `--workers`/`--shard` usage (or
  their absence) and how shard count relates to available CI runner
  capacity.
- Look at per-shard runtime in CI history: if one shard consistently
  takes noticeably longer than others, that's an imbalance problem, not
  a total-parallelism problem.
- For parallel-only failures, check whether the failing tests share
  fixtures, a database, or file-system state with other tests likely to
  run concurrently.

## Fix
- Enable Playwright's built-in worker parallelism (`--workers=N` within
  one machine) and, for larger suites, cross-machine sharding
  (`--shard=i/N` split across CI runners/matrix jobs), tuned to available
  CI capacity rather than left at a default.
- Use Playwright's test-duration-aware sharding (recent versions balance
  shards by historical test duration, not just file/test count) so wall-
  clock time per shard is roughly even; if unavailable, manually group
  known-slow tests across different shards deliberately.
- Ensure per-test isolation for anything parallel tests might contend
  over: a fresh database per worker (or per-test transactional
  rollback), unique test accounts/data per test rather than shared
  fixtures, and any external test-only resources (API keys, rate limits)
  sized for the actual parallel concurrency level, not serial usage.
- Merge shard results (JUnit/HTML reports) in a final CI step so the
  overall pass/fail status and a unified report are still visible as one
  pipeline result, not N disconnected ones.

## Pitfalls
- Increasing shard count without addressing shared-state isolation
  converts a slow, reliable suite into a fast, flaky one -- do the
  isolation work as part of introducing parallelism, not as an
  afterthought once flakiness appears.
- Over-sharding relative to available CI runner capacity (more shards
  than can actually run concurrently) doesn't reduce wall-clock time,
  just adds CI queuing/orchestration overhead.

## Verify
Compare total CI wall-clock time before and after, and run the sharded
suite several times in a row in CI (not just once) to confirm no new
parallel-only failures were introduced, checking per-shard timing
balance as part of the review.
