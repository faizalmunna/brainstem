---
name: irreversible-schema-migration-pressure-to-push-through
description: A database schema migration tied to a code migration turns out to be difficult or impossible to roll back once started, creating pressure to push through a problematic migration rather than safely abandoning it.
triggers: ["schema migration cannot be rolled back", "stuck mid migration cannot abandon safely", "irreversible database migration pressure", "migration going wrong cannot revert"]
permissions: ["READ"]
---

## Symptom

Partway through a database schema migration tied to a broader code
migration, a serious problem is discovered (data corruption risk,
unacceptable performance impact, a fundamental design flaw) -- but
rolling back cleanly isn't straightforward because the migration has
already made irreversible or hard-to-reverse changes, creating pressure
to push forward and "just get through it" rather than safely stopping.

## Likely causes

- **The migration plan didn't include an explicit rollback strategy**
  designed and tested before the migration began -- rollback was assumed
  to be "just run the reverse migration" without verifying that's
  actually safe once real production data and real-time writes are
  involved.
- **The migration involves a destructive operation** (dropping a column,
  deleting old-format data after transformation) that was performed
  before full confidence in the new schema was established, rather than
  keeping the old structure available as a safety net until the
  migration was fully validated.
- **The migration ran for long enough that new data was written in the
  new format/schema during the migration window**, so reverting to the
  old schema would require reverse-transforming that new data, which
  wasn't planned for or tested.
- **Time/business pressure pushed the team to proceed with a migration
  despite incomplete testing of the rollback path**, treating rollback
  testing as a "nice to have" that got cut when the timeline tightened.

## Diagnose

1. Assess exactly what has been changed so far and whether each change is
   genuinely reversible (data still exists in old format, no destructive
   operation yet performed) or already irreversible.
2. Check whether the original migration plan included a tested rollback
   procedure, and if so, why it isn't being executed now -- a plan that
   exists on paper but was never actually tested against real data often
   turns out not to work when actually needed.
3. Quantify the actual severity and risk of continuing forward versus
   the actual cost/risk of whatever rollback is still possible, rather
   than assuming forward is the only option under pressure.
4. Determine whether any new data has been written since the migration
   began, which would need to be accounted for in any rollback approach.

## Fix

For migrations still in progress, design (or execute an already-
designed and tested) rollback that specifically accounts for any new
data written during the migration window, not just a reversal of the
original schema change. Going forward, always design and *test* a
rollback procedure against a realistic copy of production data before
starting any migration that includes destructive operations, and
structure migrations to defer destructive/irreversible steps (dropping
old columns, deleting old-format data) until well after the new schema
has been running successfully in production, not as part of the initial
cutover. If a genuinely un-rollback-able situation is reached, the fix is
forward-only: focus all effort on stabilizing the new state as quickly
and safely as possible rather than attempting an unplanned, untested
rollback that could make things worse.

## Pitfalls

Don't perform destructive schema operations (dropping columns, deleting
old data) in the same step as the migration's initial cutover -- keep a
recovery window where the old structure remains available even after
the new one is live, specifically so a discovered problem still has a
real rollback option rather than forcing a "push through" decision.

## Verify

For future migrations, explicitly test the rollback procedure against a
production-data copy as part of migration planning, before the real
migration begins, confirming it actually works rather than assuming it
does. For the current incident, once stabilized, do a retrospective
specifically examining why rollback wasn't a viable option and feed that
into the planning process for the next migration.
