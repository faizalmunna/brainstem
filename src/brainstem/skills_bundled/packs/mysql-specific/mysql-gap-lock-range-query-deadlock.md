---
name: mysql-gap-lock-range-query-deadlock
description: Concurrent range queries or inserts under InnoDB's default isolation level deadlock unexpectedly because of gap locking that Postgres users don't expect.
triggers: ["innodb deadlock found when trying to get lock", "unexpected deadlock on insert", "gap lock deadlock mysql", "deadlock on range query mysql", "next-key lock blocking insert"]
permissions: ["READ"]
---

## Symptom
Concurrent transactions that don't appear to touch the same rows still
deadlock, with MySQL's error log or `SHOW ENGINE INNODB STATUS` reporting
`Deadlock found when trying to get lock; try restarting transaction`.
This is especially surprising to engineers coming from Postgres, where
the equivalent queries wouldn't lock the same way -- the queries involved
are often a range `SELECT ... FOR UPDATE`, an `UPDATE`/`DELETE` with a
range `WHERE` clause, or plain `INSERT`s into a table with a unique or
foreign-key index, none of which look like they should conflict.

## Likely causes
1. **InnoDB's default `REPEATABLE READ` isolation level uses next-key
   locking (record locks plus gap locks) on indexed range scans**, which
   locks not just matching rows but the "gaps" between index values in
   the scanned range, specifically to prevent phantom reads -- this is
   architecturally different from Postgres, whose MVCC implementation
   doesn't use gap locks at all, so a query pattern that's lock-free on
   Postgres can conflict on MySQL purely because of this mechanism.
2. **Two transactions insert into the same gap concurrently** -- an
   `INSERT` takes an implicit gap lock (via the insert intention lock
   mechanism) to check uniqueness/foreign-key constraints against
   neighboring index entries, so two transactions inserting different
   values that happen to fall in the same gap between existing index
   entries can block each other and, depending on ordering, deadlock.
3. **A range `UPDATE`/`DELETE` or `SELECT ... FOR UPDATE` locks a wider
   span than the author expects** because it locks gaps around every
   matching row's position in the index, not just the matching rows
   themselves, and if two such statements acquire overlapping gap locks
   in different orders, each waits on a gap the other holds.
4. **The table lacks an index that would let InnoDB narrow the locked
   range** -- without a usable index for the `WHERE` clause, InnoDB may
   lock a much broader range (or the whole table, effectively) than the
   query's logical selectivity suggests, multiplying the chance of
   overlap with concurrent transactions.

## Diagnose
- Run `SHOW ENGINE INNODB STATUS` immediately after a deadlock (or
  enable `innodb_print_all_deadlocks` to capture all of them to the error
  log) and read the `LATEST DETECTED DEADLOCK` section -- it names the
  two transactions, the specific locks each held and each was waiting
  for, and which was chosen as the deadlock victim.
- Check whether the locks involved are `gap` or `next-key` locks
  specifically (the status output labels lock type) rather than plain
  record locks -- this confirms gap locking is the mechanism, not a
  simple two-row lock-ordering deadlock.
- Run `EXPLAIN` on the queries involved to check whether they're using
  an efficient index for their `WHERE` clause -- a range scan on a
  non-indexed or poorly-indexed column locks a wider gap range than
  necessary, which is a common amplifier.
- Check the transaction isolation level in use
  (`SELECT @@transaction_isolation`, and whether it's overridden per
  session/transaction) -- confirm whether `REPEATABLE READ` (the
  default, and the level where gap locking is most aggressive) is in
  effect versus `READ COMMITTED`, which disables gap locking for
  non-unique index scans (though not entirely, e.g. foreign-key checks
  still use them).

## Fix
- Where the application's actual consistency needs don't require
  `REPEATABLE READ`'s phantom-read prevention, switching the transaction
  isolation level to `READ COMMITTED` removes gap locking for most
  statements (InnoDB uses record locks only, not gap locks, for
  non-unique index searches and range scans under `READ COMMITTED`),
  which eliminates this entire class of deadlock -- but this is a
  transaction-semantics change that needs its own review, not a blind
  toggle.
- Add or improve an index on the range-query's `WHERE` columns so InnoDB
  can lock a narrow, precise range instead of falling back to a wider
  scan, shrinking both the lock footprint and the chance of overlapping
  with concurrent transactions.
- Impose a consistent access order across transactions that touch
  overlapping ranges (e.g., always process rows/ranges in ascending key
  order across all code paths that do bulk updates), since deadlocks
  fundamentally require two transactions acquiring the same resources in
  different orders -- consistent ordering removes the cycle.
- For high-contention insert patterns into a shared gap (e.g., many
  concurrent inserts near the same auto-increment boundary or unique key
  range), consider batching inserts through a single writer/queue, or
  restructuring the unique constraint so concurrent inserts don't
  contend on the same gap.

## Pitfalls
- Treating every deadlock as an application bug to "just add a retry
  around" without understanding whether it's a gap-lock artifact --
  retries mask the symptom and add latency under contention without
  fixing a root cause that might be a straightforward index or isolation
  level change.
- Switching to `READ COMMITTED` globally without checking whether any
  code actually depends on `REPEATABLE READ` semantics (e.g., a
  multi-statement transaction that assumes a consistent snapshot across
  several reads) -- this is a real behavior change, not a free lunch, and
  needs the same scrutiny as any isolation-level change on Postgres.
- Assuming gap locking is a bug to be "fixed" the way you'd fix an
  actual defect -- it's a deliberate InnoDB mechanism for preventing
  phantom reads under `REPEATABLE READ`; the fix is choosing the right
  isolation level and access pattern for the workload, not treating gap
  locks as something to eliminate universally.

## Verify
Reproduce the original concurrent workload (the same two query patterns
run in parallel, ideally scripted rather than manual) against a staging
database with the fix applied (narrower index, adjusted isolation level,
or consistent access ordering) and confirm no deadlock occurs across
many repeated concurrent runs; if isolation level was changed, also
confirm application-level tests that depend on transaction semantics
still pass under the new level.
