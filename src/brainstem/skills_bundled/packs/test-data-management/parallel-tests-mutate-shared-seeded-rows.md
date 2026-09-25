---
name: parallel-tests-mutate-shared-seeded-rows
description: Tests pass individually but fail intermittently when run in parallel because they read and mutate the same seeded database rows concurrently.
triggers: ["tests fail only in parallel", "parallel test runs flaky database", "shared seed data race condition tests", "tests pass alone fail together"]
permissions: ["READ"]
---

## Symptom

A test suite passes reliably when run serially or in isolation, but
running it with parallel workers (multiple test processes/threads against
the same test database) produces intermittent, hard-to-reproduce
failures -- often assertion mismatches suggesting a record had a
different value than the test expected.

## Likely causes

- **Multiple parallel test workers share the same seeded database rows**
  (a fixed "test user" or "test product" record created once and reused),
  so one worker's test mutating that row (updating a balance, marking an
  order shipped) affects another worker's concurrently running test that
  assumed the row's original state.
- **Seed data is created once at suite start with fixed, well-known IDs**
  rather than generated fresh and uniquely per test/worker, making
  collisions the default rather than an edge case.
- **A test asserts on aggregate state** (a count of all rows in a table,
  a sum across records) that's sensitive to any other concurrently
  running test's inserts/deletes in the same shared table.
- **Database transactions/isolation levels used in tests don't actually
  provide the isolation assumed** -- a test wrapped in a transaction that
  gets rolled back still allows concurrent access to see uncommitted
  changes depending on the isolation level, or the rollback pattern isn't
  used consistently across all test paths.

## Diagnose

1. Reproduce with a small, deliberately parallel run (2 workers) of just
   the two suspected conflicting tests and confirm the failure occurs
   together but not individually.
2. Add logging of the exact row ID(s)/data each test reads and writes,
   and confirm across a failing parallel run whether two tests actually
   touched the same underlying data.
3. Check how seed data is provisioned -- fixed IDs created once at suite
   startup versus freshly generated per test -- and check factory/fixture
   code for hardcoded identifiers.
4. Check the test database's transaction/isolation strategy for whether
   each test's changes are actually isolated from concurrently running
   tests (per-test transaction rollback, or worker-specific schemas/
   databases).

## Fix

Generate test data with unique identifiers per test (or per parallel
worker) rather than relying on fixed, shared seed rows -- most factory
libraries support this via sequences or random generation scoped to avoid
collisions. For genuinely necessary shared reference data (lookup tables
that are read-only in practice), keep it truly read-only in tests and
never mutate it. For stronger isolation, give each parallel worker its
own database/schema (a common pattern: one database per worker, migrated
and seeded independently) rather than sharing a single database instance
across all workers.

## Pitfalls

Don't "fix" this by disabling test parallelization -- that trades a real
correctness problem for a real speed problem, and the underlying test
isolation issue will resurface the moment parallelization is
re-attempted (or masks a latent production concurrency bug that the
test was accidentally revealing). Also don't assume wrapping each test in
a transaction automatically solves isolation without confirming the
actual isolation level and rollback behavior under the specific database
and test framework combination in use.

## Verify

Run the previously-flaky tests with parallel workers repeatedly (dozens
of runs) and confirm no more intermittent failures. Deliberately increase
worker count beyond what's normally used to stress-test the isolation
fix further, since some collision patterns only appear reliably at higher
concurrency.
