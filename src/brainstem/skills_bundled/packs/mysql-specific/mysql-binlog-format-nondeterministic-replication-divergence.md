---
name: mysql-binlog-format-nondeterministic-replication-divergence
description: Replicas silently diverge from the primary because a nondeterministic function was replicated using statement-based binlog format.
triggers: ["replica data doesnt match primary", "replication silently diverged", "uuid different on replica than primary", "statement based replication nondeterministic", "checksum mismatch primary replica"]
permissions: ["READ"]
---

## Symptom
Data on a replica gradually or suddenly no longer matches the primary
for specific rows, with no replication error reported anywhere --
`SHOW REPLICA STATUS` shows no error, `Seconds_Behind_Source` looks
normal, everything appears healthy, but a row-level comparison (or a
downstream consistency check, a checksum tool, or a confused user
report about "different data depending on which read replica answered")
reveals the primary and replica actually hold different values for the
same row. This is a silent-divergence bug, not a crash or visible error,
which is what makes it dangerous -- it can run undetected for a long
time.

## Likely causes
1. **`binlog_format=STATEMENT` (or `MIXED` falling back to statement
   format for a given statement) replicated a query containing a
   nondeterministic function** -- `UUID()`, `NOW()` used inconsistently
   across a multi-statement transaction, `RAND()`, or a
   session-variable-dependent expression -- and the replica re-executed
   the *statement* rather than receiving the *already-computed result*,
   so it computed a different value than the primary did.
2. **A stored procedure or trigger with nondeterministic logic** is
   invoked by a replicated statement, and under statement-based
   replication the replica re-runs the entire procedure/trigger rather
   than replicating its row-level effects, so any nondeterminism inside
   it (not just in the top-level statement) diverges too.
3. **`INSERT ... SELECT` or similar multi-row statements interacting with
   `AUTO_INCREMENT` or ordering-dependent logic** can, under certain
   statement-based scenarios, assign different values on replica replay
   if the underlying read order isn't guaranteed identical (compounding
   with the general "no implicit order guarantee" issue in a replication
   context specifically).
4. **`MIXED` binlog format was assumed to fully protect against this**,
   but mixed format only automatically switches to row-based logging for
   statements MySQL's own detection recognizes as unsafe -- a
   nondeterministic function wrapped inside a user-defined function,
   a stored procedure, or an expression pattern outside MySQL's
   detection heuristics can still be logged as a statement and replicate
   unsafely.

## Diagnose
- Check `SHOW VARIABLES LIKE 'binlog_format'` on the primary -- confirm
  whether it's `STATEMENT`, `ROW`, or `MIXED`, since this determines
  whether divergence via this mechanism is even possible (`ROW` format
  ships computed row values directly and is immune to this specific
  failure mode).
- Search recent query logs / application code for nondeterministic
  function usage (`UUID()`, `RAND()`, `NOW()`/`CURRENT_TIMESTAMP` used
  in a way that could evaluate at different times/differently between
  primary execution and replica replay, session-variable-dependent
  expressions) in write statements, stored procedures, or triggers
  touching the affected table.
- Run a direct row-level comparison between primary and the suspect
  replica for the affected table (a checksum tool like
  `pt-table-checksum`, or a targeted manual comparison of specific rows
  reported as inconsistent) to confirm and scope the actual divergence,
  rather than relying on replication status alone, since this failure
  mode produces no replication error by design.
- If using `MIXED` format, check the primary's binlog directly
  (`mysqlbinlog` on the relevant binlog file) for the actual event type
  logged for the suspect statement (`Query_event` = statement-based,
  `Write_rows_event`/`Update_rows_event` = row-based) to confirm whether
  this specific statement was logged in the unsafe format despite mixed
  mode being enabled.

## Fix
- Switch `binlog_format` to `ROW` (or confirm it already is), which logs
  the actual computed row changes rather than the statement text, making
  the replica's applied result identical to the primary's by
  construction regardless of any nondeterminism in the originating
  statement -- this is the durable, general fix and is why `ROW` is the
  modern default recommendation.
- Where `STATEMENT` or `MIXED` format must be retained for a specific
  reason (binlog size/bandwidth constraints, tooling that parses
  statement-based binlogs), rewrite the specific nondeterministic
  statements to compute the nondeterministic value once at the
  application layer (or in a variable within the same statement) and
  pass the concrete value into the write, rather than letting the
  database compute it independently on each node.
- Audit stored procedures and triggers specifically, since they're a
  common blind spot -- nondeterminism inside a procedure invoked by a
  simple, apparently-safe top-level statement is easy to miss when
  reviewing only the calling statement.
- For already-diverged data, reconcile using the primary as the source
  of truth (re-sync the specific affected rows, or in severe cases
  rebuild the replica from a fresh primary snapshot) since there's no
  way to know which historical values on the replica are trustworthy
  once divergence is confirmed.

## Pitfalls
- Assuming `MIXED` format is a complete solution just because it exists
  to handle this exact problem -- it only auto-switches for patterns
  MySQL's statement-safety detection recognizes, which doesn't cover
  every nondeterministic pattern, especially inside stored
  procedures/UDFs.
- Discovering and fixing one instance of the bug without auditing for
  other nondeterministic-function usages across the codebase leaves
  latent, not-yet-triggered divergence risks elsewhere.
- Treating a clean `SHOW REPLICA STATUS` as proof of consistency --
  by design, this failure mode produces no replication error, so
  "replication looks healthy" is not evidence against this root cause;
  only a direct data comparison (checksum tooling) can confirm or rule
  it out.

## Verify
After switching to row-based binlog format (or fixing the specific
nondeterministic statement), run a row-level checksum comparison
(`pt-table-checksum` or equivalent) between the primary and every
replica for the affected table and confirm zero discrepancies; then
specifically re-run the original nondeterministic statement pattern
against a test primary/replica pair and confirm the replica's value now
matches the primary's exactly, not just "some" value.
