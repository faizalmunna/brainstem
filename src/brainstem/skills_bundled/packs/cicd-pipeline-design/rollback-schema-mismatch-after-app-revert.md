---
name: rollback-schema-mismatch-after-app-revert
description: Rolling back the application to a previous version breaks it because the database schema was already migrated forward and never reverted.
triggers: ["rollback broke the app with a database error", "rolled back but schema is still new version", "column not found after rollback", "reverted deploy but migrations not reverted", "rollback caused schema mismatch"]
permissions: ["READ"]
---

## Symptom
A bad deploy is rolled back to the previous application version, but the
rolled-back app immediately errors out -- missing column, unexpected
NOT NULL constraint violation, or a deserialization failure -- because the
database schema is still at the *new* version's migration state. The
"rollback" made things worse, not better, because only the app binary was
reverted while the database moved forward and stayed there.

## Likely causes
1. **Migrations run automatically as an irreversible forward-only step in
   the deploy pipeline** with no corresponding down-migration ever
   written or tested, so there is nothing for a rollback to even invoke
   even if someone thought to.
2. **The rollback procedure only reverts the application artifact**
   (container image tag, binary version) and was never designed to
   consider the database at all -- rollback in the runbook/pipeline means
   "redeploy old image," full stop.
3. **The new version's migration is backward-incompatible by design**
   (dropped a column, renamed a field, tightened a constraint) rather
   than using an expand/contract pattern, so even a correct down-migration
   would destroy data the old app needs, making a clean rollback
   impossible in principle, not just unimplemented.
4. **Migration and app deploy are decoupled in time** -- migrations run
   as a separate step (sometimes by a different team or a manual `ops`
   job) hours or days before the app deploy, so by the time a rollback is
   needed, several unrelated migrations have landed on top, making a
   single down-migration insufficient.

## Diagnose
- Identify the exact migration version applied by the bad deploy (check
  the migration tool's version table -- e.g. Flyway's `flyway_schema_
  history`, Django's `django_migrations`, Rails' `schema_migrations`) and
  compare it against what the previous app version expects.
- Check whether a down-migration exists for that version at all, and if
  it does, whether it has ever actually been run outside of local dev --
  an untested down-migration is not a safety net.
- Read the migration's SQL/DDL directly: does it drop, rename, or add a
  NOT NULL column without a default? Any of those make it
  backward-incompatible regardless of whether a down-migration exists.
- Check the deploy pipeline definition for whether "rollback" is even
  wired to a migration step, or whether it's purely
  `kubectl rollout undo` / re-point-load-balancer-at-old-image with no
  database awareness.

## Fix
Design schema changes to be rollback-safe by construction using the
expand/contract (parallel change) pattern: first deploy a migration that
only *adds* (new nullable column, new table) without removing or
tightening anything the old code depends on; deploy the app version that
uses the new schema; only after that version is confirmed stable, ship a
separate *contract* migration that removes the old column/constraint.
Under this pattern, rolling the app back to the previous version at any
point before the contract step is safe, because the old code's
assumptions about the schema still hold. Wire the pipeline's rollback
action to be schema-version-aware: it should refuse (or warn loudly) if
the currently-applied schema version is incompatible with the app version
being rolled back to, rather than silently redeploying an app that can't
run against the current schema.

## Pitfalls
- Writing a down-migration that reverses the DDL but not the data --
  e.g. dropping a column back out after the new version already wrote
  data into it loses that data permanently, which is sometimes worse than
  the original incident. Treat down-migrations for anything that touched
  live data as data-loss operations requiring the same review as the
  forward migration, not a free undo button.
- Assuming expand/contract is only needed for "big" schema changes --
  even a seemingly small change like adding a NOT NULL column without a
  default breaks the old app's INSERT statements during the rollback
  window, so the pattern needs to be the default, not an exception
  reserved for large migrations.

## Verify
Before shipping a migration, deploy it alongside the *old* app version in
a staging environment (not just the new version) and confirm the old
version still passes its full request/response test suite against the
post-migration schema -- this directly proves the rollback path works
without needing to simulate an actual incident.
