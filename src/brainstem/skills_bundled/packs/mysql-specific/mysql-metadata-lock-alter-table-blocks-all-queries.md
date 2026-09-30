---
name: mysql-metadata-lock-alter-table-blocks-all-queries
description: A single ALTER TABLE or long-running transaction on one table causes every other query against it to queue behind a metadata lock and the app appears fully down.
triggers: ["waiting for table metadata lock", "alter table hanging forever", "all queries blocked on one table", "app frozen after schema change", "lock wait timeout exceeded on unrelated query"]
permissions: ["READ"]
---

## Symptom
Shortly after starting an `ALTER TABLE` (or sometimes a seemingly
unrelated long-running transaction that merely touched the table), every
other query against that table -- reads included, from completely
different application code paths -- starts hanging or timing out. The
application appears broadly down even though only one table was being
altered, because the metadata lock queues behind it, and every new query
against that table (even simple `SELECT`s) queues behind those.

## Likely causes
1. **`ALTER TABLE` requires an exclusive metadata lock to complete**, and
   while some `ALGORITHM=INPLACE` alterations allow concurrent DML during
   the data-copy phase, they still require a brief exclusive metadata
   lock at the very start and end of the operation -- if that brief
   window coincides with (or is blocked behind) another open transaction
   holding a lock on the table, the `ALTER` itself stalls, and every
   query that comes in afterward queues behind the waiting `ALTER`
   (MySQL's metadata lock queue is generally FIFO, so later readers wait
   behind the blocked writer even though they'd otherwise be compatible
   with each other).
2. **A long-running or forgotten-open transaction elsewhere is holding a
   lock on the table** (someone left a transaction idle mid-debugging, a
   connection leaked without committing/rolling back, a slow unrelated
   query is still technically inside an open transaction) and the
   `ALTER TABLE` blocks waiting for it -- the `ALTER` isn't slow because
   of its own work, it's queued waiting for metadata lock acquisition.
3. **The `ALTER TABLE` was run without `ALGORITHM`/`LOCK` clauses
   specified**, so MySQL chose a default algorithm for that specific
   change that may require a full table rebuild (copying every row)
   rather than the fastest available in-place option, extending the
   window during which lock contention can compound.
4. **Nobody checked for existing long-running queries/transactions
   against the table before starting the `ALTER`**, so the operation was
   scheduled assuming a quiet table when in fact a background job, a
   report query, or a stuck connection was already holding it.

## Diagnose
- Check `SHOW PROCESSLIST` (or `performance_schema.threads` /
  `information_schema.processlist` for more detail) for queries in
  `Waiting for table metadata lock` state -- this confirms the pileup
  mechanism directly and shows how many queries are queued.
- Check `performance_schema.metadata_locks` (if the
  `wait/lock/metadata/sql/mdl` instrument is enabled) to see exactly
  which connection/thread currently holds the blocking lock and what
  it's doing -- this is the most direct way to identify the actual
  culprit transaction versus just seeing the queue of victims.
- Check for any long-running or idle-in-transaction session touching the
  table around the time the `ALTER` was started
  (`SHOW PROCESSLIST` filtered for `Time` and `Command: Sleep` with an
  open transaction, or `information_schema.innodb_trx` for transaction
  start time) -- a transaction open far longer than any legitimate
  query against this table would take is the likely blocker.
- Confirm which `ALGORITHM`/`LOCK` mode the `ALTER TABLE` actually used
  (check the statement as run, or `SHOW PROCESSLIST`'s `State` /
  `Info` for the ALTER's own thread) versus what was intended.

## Fix
- Before running any `ALTER TABLE` against a live, actively-queried
  table, check for and clear long-running/idle transactions against that
  table first (kill a genuinely stuck/leaked connection after
  confirming it's safe to do so), so the `ALTER` can acquire its
  metadata lock quickly rather than queuing behind unrelated blockers
  and then blocking everything else in turn.
- Explicitly specify `ALGORITHM=INPLACE, LOCK=NONE` (when the specific
  change supports it -- not all `ALTER TABLE` variants do) so MySQL
  either performs the operation with minimal locking or fails fast with
  a clear error if that mode isn't supported for this specific change,
  rather than silently falling back to a more blocking default.
- For changes that can't use a fully non-blocking in-place algorithm
  (or on versions/storage engines with more limited `ALGORITHM=INPLACE`
  support), use an external online schema-change tool (gh-ost,
  pt-online-schema-change) that performs the heavy work via a shadow
  table and triggers, keeping the exclusive-lock window to the final,
  brief cutover step only.
- Set a bounded `lock_wait_timeout` for the `ALTER` session so that if it
  does end up queued behind an unexpected blocker, it fails with a clear
  error after a reasonable wait rather than sitting indefinitely while
  accumulating a queue of blocked queries behind it.

## Pitfalls
- Killing the `ALTER TABLE` statement itself once queries start piling
  up, without addressing the root blocking transaction, can leave the
  table in a partially-altered state depending on the algorithm and
  timing -- understand what a kill mid-operation does for the specific
  algorithm in use before reaching for it as the immediate mitigation.
- Assuming `ALGORITHM=INPLACE` means "fully lock-free" -- it reduces
  locking significantly for supported operations but still requires
  brief metadata lock acquisition at start and end, which is exactly the
  window this failure mode exploits; it's not a guarantee against this
  class of incident, just a mitigation.
- Running schema changes during "off-peak" hours without actually
  checking for active long-running transactions at that time -- off-peak
  application traffic doesn't guarantee an absence of long-running
  background jobs, reports, or stuck sessions that could still block the
  `ALTER`.

## Verify
Before the next schema change against a live table, run the diagnostic
check (`performance_schema.metadata_locks` or equivalent, plus a
long-running-transaction check) as a pre-flight step and confirm no
blocking session exists; during the change, monitor `SHOW PROCESSLIST`
for any query entering `Waiting for table metadata lock` state and
confirm the queue clears within the expected, bounded window rather than
growing unboundedly.
