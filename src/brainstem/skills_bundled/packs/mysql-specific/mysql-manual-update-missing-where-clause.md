---
name: mysql-manual-update-missing-where-clause
description: A manually run production UPDATE or DELETE with a mistyped or missing WHERE clause modifies far more rows than intended and takes the API down.
triggers: ["ran update without where clause in production", "accidentally updated whole table", "manual delete affected all rows", "production database mass update by accident", "ran wrong sql against prod"]
permissions: ["READ"]
---

## Symptom
A one-off manual `UPDATE` or `DELETE` run directly against production
(via a CLI client, an admin script, or a one-time ops task) affects the
entire table, or a far larger set of rows than intended, because the
`WHERE` clause was missing, mistyped, or matched more broadly than the
author expected. The application starts erroring or behaving incorrectly
almost immediately -- often within seconds -- because the affected table
is central to core request paths (a users table, an auth/session table, a
primary entity table), turning a data-correction task into a full outage.

## Likely causes
1. **The statement had no `WHERE` clause at all**, run either by mistake
   (fingers ahead of thought while iterating on a query in a client) or
   because the author intended a scoped update but the clause was lost
   when copy-pasting/editing the statement across terminal history or a
   chat/notes tool.
2. **The `WHERE` clause matched more rows than the author modeled
   mentally** -- a condition that seemed narrow in the author's head (a
   status flag, a date range) actually matches most or all rows because
   of a data distribution the author didn't check first (e.g., assuming
   a status is rare when it's actually the default for most rows).
3. **The statement was run against the wrong environment or wrong
   database** -- a connection left open to production from an earlier
   session, or a hostname/alias that looked like staging but resolved to
   production, meant a statement developed and tested safely elsewhere
   executed for real against live data.
4. **No transaction wrapper and no dry-run step** -- the statement was
   executed directly rather than first run as a `SELECT` with the same
   `WHERE` clause to see what it would match, and without a transaction
   that could be inspected (`SELECT ... FOR UPDATE` or a row-count check)
   before committing.
5. **`autocommit` was on with no confirmation step**, so the damaging
   statement was fully committed the instant it executed, with no window
   to notice the row count reported by the client and abort before
   the change became permanent.

## Diagnose
- Confirm scope of damage immediately: check the statement actually run
  (shell/client history) and the row count MySQL reported after
  execution (`Rows matched` / `Query OK, N rows affected`) -- this alone
  often confirms whether the whole table was hit versus a large-but-bounded
  subset.
- Check whether the target table has recent binary logs available (row-
  or mixed-format binlogs specifically -- statement-based binlogs don't
  capture pre-change row values) covering the time of the bad statement,
  since row-based binlogs are the most direct path to reconstructing
  exactly which rows changed and what their prior values were.
- Check for the most recent full or incremental backup/snapshot
  predating the statement, and confirm its recency relative to how much
  additional legitimate write activity happened between that backup and
  the incident (this determines how much correct data would be lost by a
  naive restore-and-replace).
- Identify every downstream system (caches, search indexes, replicas,
  read models, queues) that may have already propagated the bad data
  before the fix lands, since restoring the source table alone doesn't
  undo changes that already fanned out.

## Fix
- Recover using row-based binlog data where available: use
  `mysqlbinlog` to extract the relevant events in the affected time
  window and reconstruct either a targeted corrective `UPDATE` (restoring
  prior values for exactly the affected rows) or a precise list of
  affected primary keys, which is far safer and faster than a full table
  restore when the binlog covers the incident.
- Where binlog-based reconstruction isn't feasible, restore the affected
  table (or a copy of it) from the most recent backup into a separate
  location, then reconcile: replay legitimate writes that happened
  between the backup and the incident (from logs, queues, or
  audit trails) before cutting back over, rather than doing a blind
  restore that silently discards valid post-backup activity.
- After recovery, invalidate/rebuild any downstream caches, search
  indexes, or derived stores that picked up the bad data before the fix
  landed, since those won't self-correct just because the source table
  did.
- Institutionalize a pre-execution habit for any manual production
  statement: run the equivalent `SELECT` with the same `WHERE` clause
  first and inspect both the row count and a sample of matched rows,
  and prefer wrapping the actual statement in an explicit transaction
  (`START TRANSACTION` ... check row count ... `COMMIT` or `ROLLBACK`)
  so there's a real inspection point before the change is permanent.

## Pitfalls
- Restoring from backup without accounting for legitimate writes that
  happened between the backup and the incident causes a second, quieter
  data-loss event stacked on top of the first one -- always reconcile
  the gap, don't just roll back the clock.
- Relying on "I'll just be careful next time" as the actual fix, instead
  of a structural safeguard (requiring `SELECT` dry-runs, requiring a
  second-person review for any manual write against production, using a
  client/tool that defaults to `sql_safe_updates=1` which rejects
  `UPDATE`/`DELETE` without a key-based `WHERE` clause) -- the discipline
  approach reliably fails again under time pressure or fatigue, which is
  exactly the condition under which this incident class tends to happen.
- Fixing the table but forgetting that the erroneous write may have
  already been replicated to read replicas and applied there too --
  replicas need the same corrective action (or will self-correct via
  replication once the primary's corrective statement replicates, but
  only if it's applied on the primary and not directly on replicas,
  which would break replication).

## Verify
Confirm every row identified as affected (via binlog reconstruction or
backup reconciliation) has its correct value restored by spot-checking a
sample against an independent source of truth (an audit log, an external
system that mirrors the data, or user reports), confirm the row count
now matches pre-incident expectations, and confirm downstream caches/
indexes/replicas reflect the corrected data -- then separately confirm
the structural safeguard (`sql_safe_updates`, mandatory dry-run, or
review requirement) is actually enabled and blocks a deliberately
unscoped test statement in a non-production environment.
