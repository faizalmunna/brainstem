---
name: ci-database-state-accumulates-across-runs
description: A CI test database is never fully reset between runs, causing accumulated state from previous runs to eventually change what a specific test observes and produce a failure with no code change involved.
triggers: ["ci test fails with no code change", "test database not reset between ci runs", "ci flaky after many runs", "accumulated state changes test result"]
permissions: ["READ"]
---

## Symptom

A test that has passed reliably for a long time suddenly starts failing
in CI with no related code change in the triggering commit, and
re-running the exact same commit sometimes passes and sometimes fails --
investigation eventually traces the difference to the state of the CI
test database itself, which has been accumulating data across many
previous runs rather than starting fresh each time.

## Likely causes

- **The CI pipeline reuses a persistent database instance/volume across
  runs** for speed (avoiding the cost of provisioning a fresh database
  every time) without a reliable full-reset step between runs.
- **A reset step exists but only truncates specific known tables**, and a
  newly added table or a table added by a dependency/migration isn't
  included in the reset list, so it accumulates rows indefinitely.
- **An auto-incrementing ID counter isn't reset along with table data**,
  so even if rows are deleted, the next inserted row gets a much higher
  ID than a test's hardcoded expectation, if any test made assumptions
  about specific ID values.
- **A previous test run was interrupted/crashed mid-test** (a CI timeout,
  an infrastructure failure) skipping its own cleanup step, leaving
  partial state that a reset step designed for graceful completion
  doesn't anticipate.

## Diagnose

1. Inspect the actual current row counts/content of the CI test
   database (if accessible) and compare against what a genuinely fresh
   database should contain -- unexpectedly high counts confirm
   accumulation.
2. Review the CI pipeline's database setup/teardown steps for exactly
   what they reset (specific tables truncated, full drop-and-recreate,
   or nothing at all beyond what the test framework's own
   transaction-rollback might provide).
3. Check whether any test makes assumptions about specific numeric IDs or
   exact row counts that would only hold true against a genuinely fresh
   database.
4. Check CI run history for any recent interrupted/crashed runs
   immediately preceding the first occurrence of the flaky failure, which
   could point at a skipped cleanup step as the trigger.

## Fix

Make database reset in CI unconditional and complete -- ideally
provisioning a genuinely fresh database (or schema) per run rather than
reusing a persistent instance with partial cleanup, if the performance
cost is acceptable; if reuse is necessary for speed, ensure the reset
step drops and recreates all tables (or truncates with identity/sequence
reset) rather than a hand-maintained partial list that can miss new
tables. Make the reset step resilient to a previous run's crash by
running it unconditionally at the *start* of each run (not relying solely
on cleanup at the *end* of the previous run, which a crash could skip).

## Pitfalls

Don't fix a specific accumulated-state failure by manually clearing the
CI database once -- without fixing the reset process itself, the same
accumulation will recur. Also, if provisioning a genuinely fresh database
per run introduces unacceptable CI time cost, weigh that tradeoff
explicitly against the cost of periodic accumulation-caused flakiness,
rather than defaulting to reuse purely for speed without considering
correctness.

## Verify

Confirm the reset step is now running at the start of every CI run
regardless of the previous run's outcome (test this explicitly by
deliberately interrupting a run and confirming the next run still starts
clean). Monitor test database row counts/state across a series of CI
runs over time to confirm they remain consistent rather than trending
upward.
