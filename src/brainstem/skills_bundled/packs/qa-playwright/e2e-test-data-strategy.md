---
name: e2e-test-data-strategy
description: Design reliable test data setup/teardown for E2E tests so they don't depend on manually-maintained fixtures or leak state between runs.
triggers: ["e2e test data setup", "test data pollution", "how to seed test data", "e2e tests interfere with each other", "shared test account problems"]
permissions: ["READ", "DATABASE"]
---

## Symptom
E2E tests fail unpredictably depending on what data currently exists in
the test environment (a previous test's leftover data, another
engineer's manual testing, a partially-failed previous run's incomplete
cleanup), or the suite requires manually maintained seed data that
drifts out of sync with what the tests actually assume.

## Likely causes
1. **Tests depend on pre-existing data** (a specific user, a specific
   product) that was manually created once and never version-controlled
   or automatically re-creatable, so the environment silently becomes
   load-bearing and fragile.
2. **Tests create data but don't clean it up**, so repeated runs
   accumulate state (duplicate accounts, orphaned records) that
   eventually causes unrelated assertions to fail (e.g. a "list has
   exactly 3 items" assertion breaking as leftover items accumulate).
3. **Shared test accounts/environments used by multiple parallel tests**
   or multiple engineers simultaneously, causing state written by one
   test/person to be read by another unexpectedly.
4. **Setup performed through the UI** (creating prerequisite data by
   clicking through the app) rather than a faster, more reliable API/
   database-level seeding step, making tests slow and coupling data setup
   to the same UI that might itself be under test.

## Diagnose
- Check whether any test assumes specific pre-existing data rather than
  creating what it needs itself.
- Check for cleanup: does each test (or a suite-level teardown) remove
  the data it created, or does the environment need periodic manual
  resets?
- Check whether tests use isolated data per test/worker (unique emails,
  unique identifiers) or share a common account/dataset across parallel
  runs.

## Fix
- Each test should create the specific data it needs at the start (via a
  fast API call or direct database seed, not by clicking through the UI)
  and treat that as the only data it depends on -- never assume
  environment state left by something else.
- Use unique, generated identifiers per test run (timestamped or
  UUID-suffixed emails/usernames) so parallel tests and repeated runs
  never collide on the same record.
- Prefer transactional rollback or a per-test/per-worker isolated
  database (or schema) over manual cleanup code, when the stack supports
  it -- guarantees isolation even if a test fails partway through and
  skips its own cleanup step.
- Where a shared environment is unavoidable (e.g. a shared staging
  environment for full-stack E2E), scope all created data with a
  recognizable prefix/tag tied to the test run, and run an automated
  sweep to remove anything older than a reasonable threshold as a safety
  net against incomplete cleanup.

## Pitfalls
- Relying solely on "cleanup at the end of the test" without a safety net
  means a test that crashes or times out mid-run leaves its data behind
  permanently -- pair per-test cleanup with a periodic/scheduled sweep for
  orphaned data as defense in depth.
- Seeding data via direct database inserts that bypass application-level
  validation/business logic can create data shapes the real application
  would never produce, masking bugs that only manifest against
  realistically-created data -- prefer seeding through the application's
  own API where practical, reserving direct DB seeding for cases where
  speed genuinely requires it and the risk is acceptable.

## Verify
Run the full suite twice in a row with no manual intervention between
runs and confirm both runs pass identically -- if the second run behaves
differently because of leftover state from the first, isolation isn't
complete yet.
