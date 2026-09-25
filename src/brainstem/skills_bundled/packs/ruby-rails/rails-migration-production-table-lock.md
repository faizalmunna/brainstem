---
name: rails-migration-production-table-lock
description: Fix a Rails migration that runs fine in development but locks a large production table for minutes and causes request timeouts during deploy.
triggers: ["migration locks table in production", "deploy hangs on migration", "ActiveRecord::LockWaitTimeout", "adding column to large table causes downtime", "migration works in dev but times out in prod"]
permissions: ["READ"]
---

## Symptom
A migration (adding a column, adding an index, adding a NOT NULL
constraint or default) runs in a fraction of a second against the
development database, but during production deploy it either hangs for
minutes, times out with `ActiveRecord::LockWaitTimeout` /
`ActiveRecord::StatementTimeout`, or briefly takes the whole app down as
web requests queue up behind the migration's lock on a large,
high-traffic table.

## Likely causes
1. **Development's database has a few hundred or thousand rows; the
   production table has millions** -- operations that are O(rows) at the
   database level (adding a column with a non-null default pre-Postgres
   11/pre-MySQL 8 semantics, backfilling data in the same migration,
   building an index) take proportionally longer and hold their lock the
   whole time.
2. **Adding an index without `algorithm: :concurrently` (Postgres) or an
   online DDL option (MySQL)** takes a full table lock (or a much
   stronger lock than necessary) for the index build's entire duration,
   blocking writes -- and on Postgres, `CREATE INDEX CONCURRENTLY` cannot
   run inside the transaction Rails wraps migrations in by default.
3. **Adding a foreign key or a `NOT NULL` constraint with `validate: true`
   (the default) forces a full table scan to validate existing rows while
   holding a lock**, which on a large table takes long enough to exceed
   the app's statement timeout or the connection pool's patience, even
   though the schema change itself is instant.
4. **The migration combines a schema change and a data backfill in one
   step** (e.g. `add_column` then immediately `Model.update_all(...)` in
   the same migration file), turning a fast DDL operation into a
   long-running, lock-holding write across every row.
5. **Production's database version/engine has different locking
   semantics than development's** -- e.g. developing against SQLite or an
   older Postgres locally while production runs a Postgres version with
   different (or the same, but untested) lock-escalation behavior for the
   specific operation.

## Diagnose
- Check the row count of the target table in production
  (`SELECT reltuples FROM pg_class WHERE relname = 'table_name';` on
  Postgres, or `SELECT COUNT(*)` for an exact but slower count) versus
  development -- an order-of-magnitude difference is the first clue.
- Read the migration's generated SQL (`rails db:migrate:status` plus
  reading the migration, or run with `ActiveRecord::Migration.verbose = true`
  against a production-sized snapshot/replica) and identify which
  statement is the expensive one: index creation, constraint validation,
  or a bulk `UPDATE`.
- Check the database's lock/activity view during a rehearsal run against
  a production-sized copy: `SELECT * FROM pg_locks WHERE NOT granted;`
  and `pg_stat_activity` on Postgres, or `SHOW PROCESSLIST`/
  `information_schema.INNODB_TRX` on MySQL, to see exactly what's blocked
  waiting on the migration's lock.
- Confirm whether the migration runs inside Rails' default
  transactional-migration wrapper -- some operations (like Postgres
  `CREATE INDEX CONCURRENTLY`) are outright rejected or silently run
  non-concurrently inside a transaction, which is easy to miss until
  production.

## Fix
- Add indexes with `algorithm: :concurrently` on Postgres (and
  `disable_ddl_transaction!` at the top of that migration, since
  concurrent index builds can't run inside a transaction), or the
  equivalent online-DDL tooling on MySQL (`ALGORITHM=INPLACE, LOCK=NONE`
  where supported), so the index builds without holding a blocking lock
  for its full duration.
- Split schema changes from data changes into separate migrations/deploys:
  add a column as nullable with no default (instant metadata-only change
  on modern Postgres/MySQL), backfill the data in batches via a rake task
  or background job with sleep/throttling between batches, then add the
  `NOT NULL` constraint (or `validate: false` follow-up validation) once
  backfilled.
- For foreign keys and check constraints on large tables, add them with
  `validate: false` first (instant), then validate in a separate
  migration/statement (`ALTER TABLE ... VALIDATE CONSTRAINT`) which takes
  a lock but only a lighter one that doesn't block writes the same way.
- Rehearse the migration against a realistic production-sized copy
  (a recent anonymized snapshot or replica) before deploying, with the
  same database version and lock timeout settings production uses, so
  the cost is known ahead of time rather than discovered during deploy.

## Pitfalls
- `algorithm: :concurrently` on Postgres can fail partway through and
  leave an invalid index behind (`INVALID` in `pg_indexes`) that silently
  isn't used by the query planner -- after any concurrent index build,
  check for and drop/rebuild invalid indexes rather than assuming success
  because the migration "completed."
- Batched backfills without a small delay between batches can still
  saturate replication lag or I/O on a busy production database even
  though no single batch holds a long lock -- monitor replication lag
  during the backfill, not just lock wait time.
- Running the rehearsal against a production snapshot but with a
  different database version, extension set, or statement_timeout than
  production actually uses gives false confidence -- match the
  configuration, not just the row count.

## Verify
Run the migration against a production-sized replica or recent snapshot
with the same `statement_timeout`/`lock_timeout` settings production
enforces, and confirm it completes without hitting a timeout and without
another concurrent session observing lock waits longer than the app's own
request timeout (check `pg_locks`/`SHOW PROCESSLIST` during the run, or
time a concurrent read/write against the same table while the migration
executes).
