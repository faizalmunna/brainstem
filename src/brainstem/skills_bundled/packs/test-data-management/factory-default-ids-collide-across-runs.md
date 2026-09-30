---
name: factory-default-ids-collide-across-runs
description: A test data factory generates objects with hardcoded or low-entropy identifiers that collide across test runs, causing unique-constraint violations or unexpected data overwrites.
triggers: ["factory generated duplicate id", "unique constraint violation in tests", "factory bot email already taken", "test data collision across runs"]
permissions: ["READ"]
---

## Symptom

Tests intermittently fail with a database unique-constraint violation (a
duplicate email, a duplicate SKU) or with an assertion mismatch caused by
one test's created record silently colliding with and overwriting
another's, despite each test appearing to create its own independent test
data via a factory.

## Likely causes

- **A factory's default field values are static strings** (`email:
  "test@example.com"`) rather than generated per-invocation, so any two
  tests (or two runs against a persistent test database) that don't
  override the field collide.
- **A factory uses a low-entropy or narrow-range sequence/counter** for
  uniqueness (a simple incrementing integer reset per test run) that
  works within a single run but collides across parallel runs or against
  a database that isn't fully reset between runs.
- **The test database isn't actually reset between test runs** (a
  persistent shared test environment, a CI cache that isn't cleared),
  so a "unique" value generated relative to an assumed-empty database
  collides with leftover data from a previous run.
- **A factory's uniqueness scope doesn't match the actual database
  constraint's scope** -- e.g. generating a "unique" value per table when
  the real constraint is unique per tenant/organization, or vice versa,
  producing either unnecessary collisions or false confidence.

## Diagnose

1. Reproduce the collision by running the same test (or the same factory
   call) twice against the same database state without an intervening
   reset, and confirm whether it fails the second time.
2. Inspect the factory's default value generation for the specific
   colliding field -- static string, counter, or genuinely randomized/
   high-entropy value (UUID, random string with sufficient length).
3. Check the test suite's database setup/teardown configuration for
   whether it actually truncates/resets relevant tables between runs, or
   only between individual tests within a single run.
4. Compare the factory's uniqueness scope against the actual database
   constraint definition to confirm they match.

## Fix

Generate factory default values with genuinely high-entropy uniqueness
(a UUID, a sufficiently long random string, or a counter combined with a
run-specific random seed) rather than static strings or narrow sequences,
so collisions become practically impossible even across parallel or
back-to-back runs without a full reset. Ensure the test database is
actually reset (truncated or recreated) at an appropriate boundary (per
test, per suite run) matching what the factory's uniqueness assumptions
require, and treat any persistent shared test database as a database that
needs the same collision-avoidance rigor as concurrent parallel runs.

## Pitfalls

Don't fix a specific field's collision by hardcoding a "more unique"
but still static replacement string -- that just narrows the window
until the next collision; use a generation strategy that's inherently
collision-resistant rather than a slightly-less-likely static value.
Also, when adding randomization, keep test failures reproducible by
logging or seeding the random generator deterministically when a test
does fail, so a flaky-looking failure can actually be reproduced and
debugged rather than becoming untraceable.

## Verify

Run the same test or factory call many times in a tight loop against a
non-reset database and confirm no collisions occur across a realistic
number of iterations. Run the full suite in parallel (if applicable)
multiple times and confirm no unique-constraint violations appear.
