---
name: rollback-blocked-by-run-forward-data-or-config-migration
description: A dependency upgrade is reverted cleanly at the code level, but the rollout cannot be rolled back because running the upgrade already moved data, schema, or configuration that the old version can no longer read.
triggers: ["we can't roll back the upgrade because the migration already ran", "reverting the dependency breaks because data changed", "can't downgrade because persisted data is now in the new format", "schema moved forward and the old version can't read it"]
permissions: ["READ"]
---

## Symptom

The upgraded dependency causes a problem in production and the team tries
to roll back -- reverting the code, redeploying the old version, restoring
the old config. The rollback itself breaks. The upgrade's side effect was a
state migration, and either the old version cannot read the newly written
data, the current config is rejected or silently misinterpreted by the old
code, or newly written rows and blobs are now in a format only the new
version understands. What looked like a code-level revert was never atomic
with the data-level change the new version already caused.

## Likely causes

- **The dependency performs implicit migrations on read or startup** -
  an index rebuild, a metadata or lock-file rewrite, a cache re-shape, a
  serialization schema change - so merely running the new version once
  permanently rewrites state the old version can no longer open.
- **The rollout promoted data and config *and* code as a unit, but the
  rollback plan only reverted the code,** assuming the state change was
  reversible in lockstep with it.
- **The application writes new-format data eagerly** the moment the new
  version runs (new defaults, new enum values, wider or renamed columns),
  so the old runtime chokes on data that now exists in production even if
  the binary is downgraded.
- **An app config schema was migrated in place** (new fields, renamed
  flags, stricter validation), and the old code rejects the new config or
  silently applies different defaults to it, so behavior changes after a
  downgrade even with identical code.

## Diagnose

1. Identify every persistent artifact the dependency and the app touch,
   and whether any version boundary rewrites them on startup or first write
   (check the upgrade's migration notes; watch for larger/smaller stores,
   modified metadata timestamps, or rewritten lock files after first run).
2. Rehearse the rollback before relying on it: deploy the old version
   against post-upgrade production state in staging-clone data and watch
   whether it starts, reads, and writes correctly.
3. Diff the current config against what the previous version accepted
   (schema keys, defaults, validation rules) to check whether old code
   would misinterpret it.
4. Check whether the app itself persists new-format data independently of
   the dependency's behavior (grep for newly added persisted fields,
   enums, or default values written on the upgrade's code path).

## Fix

Make rollback part of the upgrade plan, tested rather than assumed: define
it as code, data schema, and config all reverting together, and run a full
old-version execution against post-upgrade snapshots in staging before
shipping. Where the dependency genuinely rewrites state irreversibly on
startup, treat the upgrade as effectively irreversible and plan forward:
backups taken at a restore point *before the first new-version process
runs* (not at deploy start), exhaustive pre-verification, and an explicit,
documented decision that a downgrade requires restoring those backups and
accepting the data delta. For your own write formats, keep new writes
readable by the old version for one release (a compatibility flag or a
write-path option) so code and data can revert independently rather than
only in one fixed order.

## Pitfalls

A "rollback" that restores a pre-deploy backup can itself be destructive:
if writes continued between the upgrade and the rollback decision,
restoring an old snapshot discards real user data and the team is now
choosing between "replay forward" and "lose the delta." That tradeoff must
be decided explicitly by someone who can weigh it -- not made accidentally
by an operator restoring whichever snapshot looks newest.

## Verify

Rehearse the rollback in staging: snapshot production-shaped state, run the
new version to trigger the migration, then run the old version against that
snapshot and confirm it starts and serves pre-upgrade behavior without
corruption. Record the exact backup and restore steps that make the same
sequence safe in production, so rollback is executable under time pressure
instead of discovered mid-incident.