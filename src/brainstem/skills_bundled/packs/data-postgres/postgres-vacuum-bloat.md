---
name: postgres-vacuum-bloat
description: Diagnose Postgres table/index bloat and autovacuum falling behind, which causes slow queries and wasted disk space that a naive index/query fix won't solve.
triggers: ["postgres table bloat", "autovacuum not keeping up", "postgres disk space growing", "vacuum full needed", "postgres dead tuples"]
permissions: ["READ", "DATABASE"]
---

## Symptom
A table (or its indexes) consumes far more disk space than its actual
data would suggest, queries against it slow down over time even without
data-volume growth explaining it, and/or `autovacuum` appears to be
running but not keeping the table's dead-tuple count under control.

## Likely causes
1. **High update/delete churn on a table** (Postgres's MVCC model creates
   a new row version on every update rather than modifying in place,
   leaving the old version as a "dead tuple" until vacuumed) faster than
   autovacuum can clean it up.
2. **Autovacuum settings too conservative for the table's actual write
   volume** -- the default thresholds/scale factors are tuned for
   moderate workloads and can fall behind on very high-churn or very
   large tables without per-table tuning.
3. **A long-running transaction preventing vacuum from cleaning up dead
   tuples** -- Postgres can't remove a dead tuple that might still be
   visible to an older, still-open transaction, so one forgotten
   long-running transaction can block cleanup across the whole database.
4. **Bloated indexes specifically** (not just the table) -- indexes
   accumulate their own bloat from updates/deletes and don't always
   shrink even after the table itself is vacuumed.

## Diagnose
- Check `pg_stat_user_tables` for `n_dead_tup` (dead tuple count) relative
  to `n_live_tup`, and `last_autovacuum`/`autovacuum_count` to see whether
  autovacuum is running at all and how recently.
- Check for long-running transactions via `pg_stat_activity`
  (`xact_start` far in the past) that could be holding back vacuum's
  ability to clean up -- this is a frequent, easy-to-miss root cause
  distinct from autovacuum settings themselves.
- Estimate actual bloat (several well-known community queries compute
  approximate table/index bloat from `pg_class`/`pg_stats`) rather than
  guessing from disk usage alone, since some disk growth is normal and
  expected.
- Check per-table autovacuum settings (`autovacuum_vacuum_scale_factor`,
  `autovacuum_vacuum_cost_delay`) against the table's actual size and
  write rate -- defaults that work for a small table can be far too slow
  for a very large, high-churn one.

## Fix
- For a stuck long-running transaction, identify and terminate it (after
  confirming it's safe to do so) so vacuum can resume cleaning up dead
  tuples that were being held back -- this alone often resolves bloat
  that looked like an autovacuum tuning problem.
- Tune autovacuum more aggressively on specific high-churn tables (lower
  `autovacuum_vacuum_scale_factor` so it triggers sooner relative to
  table size, adjust `autovacuum_vacuum_cost_delay`/`cost_limit` to let
  it work faster) rather than changing global defaults for the whole
  database.
- For already-severe bloat that regular vacuum can't reclaim (vacuum
  marks space reusable but doesn't shrink the file on disk), use
  `VACUUM FULL` (which rewrites the table and requires an exclusive lock
  -- schedule for a maintenance window) or an online alternative like
  `pg_repack` that avoids the long exclusive lock for tables that can't
  tolerate downtime.
- Rebuild bloated indexes with `REINDEX CONCURRENTLY` (available in
  modern Postgres versions) to reclaim index-specific bloat without a
  full table rewrite.

## Pitfalls
- Running `VACUUM FULL` on a large, actively-used table takes an
  exclusive lock for its duration, blocking all reads and writes -- never
  run it against a production table without a planned maintenance window
  or an online alternative (`pg_repack`) for tables that can't tolerate
  that.
- Tuning autovacuum more aggressively without addressing an underlying
  long-running-transaction problem treats a symptom that will recur --
  always rule out blocked vacuum from open transactions first.
- Global autovacuum tuning changes affect every table in the database,
  including ones that were working fine -- prefer per-table
  (`ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = ...)`) tuning
  for a specific problem table.

## Verify
After remediation, monitor `n_dead_tup` for the affected table over
time and confirm it stabilizes at a reasonable level relative to
`n_live_tup` rather than continuing to grow, and confirm query latency
against that table returns to expected levels.
