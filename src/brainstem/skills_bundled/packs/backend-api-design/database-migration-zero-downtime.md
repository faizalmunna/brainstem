---
name: database-migration-zero-downtime
description: Design a schema migration (column rename, type change, adding a NOT NULL column, dropping a column) that doesn't lock a large table or break the currently-running application version.
triggers: ["migration locks table", "zero downtime migration", "add not null column large table", "rename column safely", "migration breaks running app", "database deploy downtime"]
permissions: ["READ", "DATABASE"]
---

## Symptom
A schema migration either locks a large table for an unacceptable amount
of time during deploy (blocking reads/writes), or breaks the currently-
running (old) version of the application for the window between the
migration running and the new application code deploying, because the old
code still expects the previous schema.

## Likely causes
1. **A single migration that both changes the schema and requires the
   new application code simultaneously** -- e.g. renaming a column: the
   old app code reads/writes the old name, the new app code the new name,
   and there's no version of the schema both can work against during a
   rolling deploy.
2. **Adding a `NOT NULL` column without a default, or with a default that
   requires rewriting every existing row**, on a large table -- some
   databases lock the table for the duration of the rewrite; even ones
   that support fast defaults can still lock for validation passes.
3. **Adding an index without `CONCURRENTLY`** (Postgres) or the
   equivalent online-index-build option, taking a lock that blocks writes
   for the duration of the index build on a large table.
4. **Changing a column's type in place** (e.g. `int` -> `bigint`) which
   typically requires a full table rewrite and an exclusive lock for the
   duration on databases without online type-change support.

## Diagnose
- Identify which category the migration falls into: a pure additive
  change (new nullable column, new table) is generally safe; a rename,
  type change, `NOT NULL` addition, or new index on an existing large
  table needs the patterns below.
- Check the table's row count and write volume -- the acceptable
  approach differs significantly between a rarely-written 10-row config
  table and a heavily-written multi-million-row table.
- Check whether the migration tooling in use runs migrations
  automatically during deploy in a way that could overlap with old
  application instances still running against the pre-migration schema.

## Fix
- **Renames**: never rename in place. Add the new column, dual-write to
  both old and new columns from the application (deploy this first),
  backfill existing rows in batches, deploy application code that reads
  from the new column (still dual-writing), then stop writing to the old
  column, then drop it -- each step is its own safe, reversible
  deployment.
- **Adding `NOT NULL`**: add the column as nullable first, backfill in
  batches (not one giant `UPDATE`), then add the `NOT NULL` constraint
  (with a `CHECK` constraint added `NOT VALID` then validated separately,
  on databases that support it, to avoid a full-table lock during
  validation).
- **New indexes**: build with the online/concurrent option
  (`CREATE INDEX CONCURRENTLY` in Postgres) even though it's slower and
  can't run inside a transaction -- it avoids blocking writes during the
  build.
- **Type changes**: on databases without a fast online type-change path,
  use the same add-new-column-backfill-swap pattern as renames rather
  than an in-place `ALTER COLUMN TYPE`.
- Batch backfills in bounded chunks (e.g. 1,000-10,000 rows per
  transaction with a brief pause) rather than one large `UPDATE`, to
  avoid long-held locks and excessive replication lag.

## Pitfalls
- Deploying the schema migration and the application code that depends on
  it in the same release without a dual-write/backfill window leaves a
  gap (however short) where old app instances mid-rolling-deploy break
  against the new schema, or new instances break against the old one.
- `CREATE INDEX CONCURRENTLY` can fail partway through and leave an
  invalid index behind that still consumes space and write overhead
  without being usable -- check for and clean up invalid indexes after a
  failed concurrent build, don't just retry blindly.
- Batched backfills that don't checkpoint progress can restart from
  scratch if interrupted -- track progress (e.g. by ID range or a
  "backfilled" flag) so a resumed backfill continues rather than
  reprocessing already-done rows.

## Verify
Run the migration against a production-sized (or realistically scaled)
copy of the table and measure actual lock duration/write blocking during
each step; for the dual-write pattern, verify with a query that old and
new columns match for all rows before proceeding to drop the old one.
