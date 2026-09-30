---
name: mysql-auto-increment-int-exhaustion
description: Inserts start failing with a duplicate-key or out-of-range error because an auto-increment primary key hit the maximum value of its integer type.
triggers: ["duplicate entry for key primary auto increment", "out of range value for auto increment column", "auto increment stopped working", "primary key exhausted", "cannot insert row id max reached"]
permissions: ["READ"]
---

## Symptom
`INSERT` statements against a table start failing -- either with
`Duplicate entry 'N' for key 'PRIMARY'` (the auto-increment counter has
wrapped to a value that already exists, on an unsigned column overflow
in some configurations) or with an explicit
`Out of range value for column 'id'` error -- on a table that has been
accumulating rows for a long time (often years) with no prior issue,
typically on a high-write-volume table like an events, logs, or
activity-feed table.

## Likely causes
1. **The auto-increment column was defined as a signed or unsigned
   `INT` (32-bit)**, whose maximum value (2,147,483,647 signed /
   4,294,967,295 unsigned) seemed effectively unlimited when the table
   was designed, but a high-volume table (especially one with a high
   insert rate, or one where `AUTO_INCREMENT` values are burned quickly
   due to failed/rolled-back transactions still consuming an ID) reaches
   that ceiling faster than anyone modeled.
2. **`AUTO_INCREMENT` values are consumed even by transactions that roll
   back** -- InnoDB's auto-increment counter (in the default,
   non-legacy locking mode) doesn't reuse IDs from failed inserts, so a
   workload with a meaningfully high rate of insert retries/rollbacks
   burns through the ID space measurably faster than the net row count
   would suggest, making capacity planning based on "current row count"
   an underestimate.
3. **The table was migrated/copied at some point (a schema change tool,
   a backup-restore, a cross-region copy) in a way that reset or
   mismatched the `AUTO_INCREMENT` starting value**, causing IDs to
   collide with existing rows sooner than the natural growth curve would
   suggest, producing duplicate-key errors before the type's true
   numeric ceiling is reached.
4. **A batch/bulk insert process explicitly sets high ID values** (for a
   migration, a data import with pre-assigned IDs, or a
   multi-region/multi-writer ID allocation scheme using large offsets
   per shard) that pushes the effective ceiling reached far sooner than
   organic single-increment growth would.

## Diagnose
- Check the column's exact type and signedness:
  `SHOW CREATE TABLE <table>` and confirm whether it's `INT` vs
  `BIGINT`, and `SIGNED` vs `UNSIGNED` -- this determines the actual
  ceiling (roughly 2.1B for signed INT, 4.3B for unsigned INT, and
  effectively unlimited for practical purposes with `BIGINT UNSIGNED`).
- Check the current auto-increment value and compare against the type's
  maximum: `SELECT AUTO_INCREMENT FROM information_schema.tables WHERE
  table_schema = '<db>' AND table_name = '<table>'`, and project the
  remaining headroom against the table's actual insert rate
  (from monitoring or binlog event counts over a recent window) to
  quantify how much runway remains, or confirm it's already exhausted.
- Check whether row count is far below the current `AUTO_INCREMENT`
  value -- a large gap between actual row count and the current
  counter value indicates significant ID consumption from
  rollbacks/deletes/failed inserts rather than net table growth, useful
  for understanding why exhaustion happened faster than expected.
- Check the exact error: a `Duplicate entry` error on an unsigned column
  suggests the counter actually wrapped/wrapped-adjacent behavior or a
  manually-set high value collided with existing rows, while an explicit
  `Out of range value` error confirms the type's hard ceiling was
  reached and MySQL refused to generate a value at all.

## Fix
- Widen the column type to `BIGINT UNSIGNED` (`ALTER TABLE <table>
  MODIFY id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT`), which for nearly
  all realistic workloads provides effectively unlimited headroom (over
  18 quintillion), and treat this as the durable fix rather than any
  workaround that delays but doesn't remove the ceiling.
- Before altering a large, actively-written table, plan the `ALTER
  TABLE` as an online schema-change operation (via a tool like gh-ost or
  pt-online-schema-change, or native `ALGORITHM=INPLACE` where
  supported for this specific change) rather than a blocking direct
  `ALTER`, since this table is by definition high-write-volume and a
  long metadata lock would be highly disruptive.
- If exhaustion is imminent and the full migration can't land before the
  ceiling is hit, as a stopgap, audit for and reduce unnecessary ID
  consumption (e.g., an insert-retry loop that doesn't need to actually
  attempt the insert before validating) to buy time -- but treat this as
  a bridge to the real fix, not a substitute for widening the column.
- For new tables (or as part of this remediation), default to `BIGINT
  UNSIGNED` for any auto-increment primary key on a table expected to
  have meaningful sustained write volume, rather than `INT`, to avoid
  needing this exact migration again.

## Pitfalls
- Widening the column type without accounting for the application-level
  and cross-table impact of ID values exceeding the old `INT` range --
  any foreign key columns, application-side type declarations (some
  language/ORM integer types silently truncate or misrepresent values
  beyond 32-bit signed range), or external systems that stored/cached
  this ID as a 32-bit type elsewhere need auditing too.
- Running the `ALTER TABLE` as a blocking operation on a live
  high-volume table causes exactly the kind of long-lock disruption this
  fix is trying to avoid -- always use an online schema-change approach
  for a table active enough to have hit this problem in the first place.
- Treating "resetting" the auto-increment counter downward (assuming
  gaps from deletes can be reclaimed) as a fix -- MySQL doesn't safely
  support reusing auto-increment values from deleted rows in a way that
  avoids collision risk with foreign key references or cached IDs
  elsewhere, and this doesn't address the underlying type ceiling anyway.

## Verify
After the type change, confirm `SHOW CREATE TABLE` reflects `BIGINT
UNSIGNED`, confirm the current `AUTO_INCREMENT` value is preserved
(continuity, not reset to 1) via `information_schema.tables`, and insert
a test row confirming the returned ID continues the existing sequence
correctly; separately, confirm any downstream system (application
models, foreign key columns, caches) that references this ID has been
audited to handle the wider value range without truncation.
