---
name: fixture-stale-after-schema-migration
description: Tests start failing for reasons unrelated to the code under test because a fixture file or seed script wasn't updated to match a recent database schema migration.
triggers: ["fixture out of date after migration", "seed data missing new column", "tests fail after migration unrelated to change", "fixture schema mismatch"]
permissions: ["READ"]
---

## Symptom

After a database schema migration is merged (adding a required column, a
new foreign key constraint, renaming a field), tests unrelated to the
migration's actual feature start failing -- with error messages about a
missing column, a constraint violation, or unexpected null values, none
of which point directly at the migration as the cause.

## Likely causes

- **A static fixture file (JSON/YAML/SQL seed data) doesn't include a
  newly added required column**, so loading the fixture either fails
  outright or succeeds with an unintended null/default value that later
  code doesn't expect.
- **A new NOT NULL constraint or foreign key was added to a table that
  fixtures populate**, and the fixture's existing rows don't satisfy the
  new constraint, causing a failure at fixture-load time rather than in
  the test logic itself.
- **A field rename in the migration wasn't mirrored in fixtures/factories**
  that still reference the old field name, silently populating the old
  (now nonexistent, or newly repurposed) field name instead of the
  correct one.
- **Fixtures are maintained in a different location/format/process than
  the schema migrations themselves**, so there's no structural link
  ensuring the two stay in sync -- a migration PR can merge cleanly
  without anyone being prompted to check fixtures at all.

## Diagnose

1. Confirm the failing tests' errors point at the specific table/column
   affected by a recent migration by checking error messages against the
   migration's actual diff.
2. Check whether fixture files or seed scripts reference the affected
   table and whether they were updated in the same PR as the migration
   (or a follow-up one).
3. Try loading the fixture data directly against the current schema
   (outside of the full test run) to isolate whether the failure is at
   fixture-load time versus later in test execution.
4. Search across the codebase for every place static fixture data is
   defined for the affected table, since there may be multiple
   fixture sources (unit test fixtures, integration test seeds, local dev
   seed scripts) that need the same update.

## Fix

Update every fixture/seed source affected by the migration in the same
change as the migration itself, treating fixture updates as a required
part of any migration's PR checklist rather than a follow-up
afterthought. Where practical, generate fixture data programmatically
from factories that build against the current schema (rather than
hand-maintained static files), since a factory referencing model
definitions directly is far less likely to silently drift out of sync
with schema changes than a static file is. For teams with many fixture
sources, consider a single source of truth for common seed data reused
across test types, rather than several independently maintained copies.

## Pitfalls

Don't fix an individual fixture-load failure by relaxing the new
constraint just to make old fixtures pass -- if the constraint is
genuinely correct for real data, weakening it defeats the purpose of
adding it; fix the fixture data instead. Also don't let fixture updates
become an afterthought merged separately and later than the migration --
a gap between the two, even briefly, breaks the whole suite for anyone
who pulls the migration without the fixture fix.

## Verify

Run the full test suite (not just the tests that were failing) after
updating fixtures to confirm no other latent references to the old
schema shape remain. Confirm the migration and fixture updates are
reviewed and merged together (or the fixture update is clearly linked as
a required follow-up before the migration is considered complete) as a
process check for future migrations.
