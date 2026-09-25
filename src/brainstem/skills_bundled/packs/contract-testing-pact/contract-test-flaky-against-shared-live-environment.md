---
name: contract-test-flaky-against-shared-live-environment
description: Provider verification is intermittently flaky because it runs against a shared live staging environment instead of an isolated in-process provider with controlled state.
triggers: ["pact verification flaky in ci", "contract test intermittent failure shared environment", "provider verification fails randomly depending on staging data", "flaky pact test because of shared test environment"]
permissions: ["READ"]
---

## Symptom

Provider verification passes sometimes and fails other times with no
code change in between -- re-running the exact same CI job on the exact
same commit produces a different result. Investigating shows the
verification suite points at a shared staging/test environment's URL
rather than spinning up the provider in-process or against an isolated
test instance, so results depend on whatever data and traffic happen to
be present in that shared environment at the moment the job runs.

## Likely causes

- **Verification is configured with a `providerBaseUrl` pointing at a
  long-lived shared staging deployment** instead of starting the
  provider application as part of the test run, so concurrent test runs,
  other teams' manual testing, or scheduled jobs against that same
  environment mutate data mid-verification.
- **Provider state setup writes to the shared environment's real
  database** without cleanup, so state from a previous (possibly failed
  or concurrent) verification run persists and either satisfies or
  breaks the current run's assumptions unpredictably.
- **Multiple CI jobs (different branches, different PRs) run
  verification against the same shared environment concurrently**, so
  one job's provider-state setup overwrites or deletes data another
  concurrently-running job's interaction depends on.
- **The shared environment has its own independent deployment cadence**,
  so the code actually running there during verification may not even
  match the commit CI thinks it's testing, making failures impossible to
  reproduce locally against the same commit.

## Diagnose

1. Check the verifier configuration for `providerBaseUrl` (or equivalent)
   -- if it's a static shared hostname rather than `localhost` plus a
   port the CI job itself started, that's the structural cause.
2. Re-run the identical failing verification job twice in immediate
   succession and diff the two result sets -- if failures differ between
   runs with no code change, that's strong confirmation of environment
   non-determinism rather than a genuine contract violation.
3. Check CI logs' timestamps for verification runs against overlapping
   time windows from different branches/PRs hitting the same environment,
   and correlate failure timing with concurrent runs.
4. Query the shared environment's actual data at the moment of a failure
   (if still accessible) and compare it against what the failing
   interaction's provider state was supposed to set up -- a mismatch
   confirms interference rather than a real code defect.

## Fix

Run provider verification against an instance of the provider started
fresh for that CI job -- in-process where the framework supports it, or
in an ephemeral container/test database spun up and torn down per run --
so provider state setup operates on data nothing else can touch. Where a
true in-process run isn't feasible (e.g. verifying against a deployed
container image as an integration smoke check), use a dedicated,
single-tenant ephemeral environment per CI run (e.g. a fresh
docker-compose stack or a per-PR namespace) rather than a long-lived
shared one, and ensure the database/state layer is reset or seeded fresh
at the start of every run.

## Pitfalls

Don't "fix" the flakiness by adding retries around the verification step
-- retrying a test that fails due to shared mutable state just hides the
non-determinism and can let genuine contract violations slip through on
a lucky retry. Also don't solve it by adding delays/locks to serialize
access to the shared environment across CI jobs -- that trades flakiness
for slow, queued CI without addressing the real problem, which is that
contract verification needs an isolated, disposable backend, not
coordinated access to a shared one.

## Verify

Run the same verification job many times in a tight loop (locally or via
a repeated CI trigger) with the isolated setup in place and confirm
100% consistent results with no code changes between runs. Additionally,
trigger two verification runs concurrently (simulating two PRs) against
the new isolated setup and confirm neither run's results are affected by
the other, which was not true under the shared-environment setup.
