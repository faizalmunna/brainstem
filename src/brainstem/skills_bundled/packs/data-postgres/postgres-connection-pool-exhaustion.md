---
name: postgres-connection-pool-exhaustion
description: Diagnose "too many connections" / connection pool exhaustion errors against Postgres, distinguishing a genuine capacity problem from a connection leak.
triggers: ["too many connections postgres", "connection pool exhausted", "fatal sorry too many clients already", "database connection timeout", "pgbouncer connections full"]
permissions: ["READ", "DATABASE"]
---

## Symptom
The application (or Postgres itself) throws connection errors --
"FATAL: sorry, too many clients already," a connection pool timeout
waiting for an available connection, or new requests failing while
existing ones continue to work -- typically appearing under load or after
running for a while, not immediately at startup.

## Likely causes
1. **A genuine capacity mismatch**: the number of application instances x
   their configured pool size exceeds Postgres's `max_connections` (or a
   pooler's configured limit), which was sized for a smaller deployment
   and never revisited after scaling out.
2. **A connection leak** -- code that acquires a connection/transaction
   and doesn't reliably release it on all code paths (especially on
   exceptions), so connections accumulate as "in use" even though the
   application has moved on, until the pool is exhausted.
3. **Long-running or abandoned transactions** holding a connection open
   far longer than the actual query needs -- a transaction left open
   after a slow external call inside it, or a bug where `COMMIT`/
   `ROLLBACK` is never reached on some path.
4. **No connection pooler (like PgBouncer) in front of Postgres** for a
   workload with many short-lived application processes/instances, each
   opening its own direct connections, multiplying real connection count
   beyond what a pooler would allow through.
5. **A pool sized far larger than actually useful** on the application
   side, based on a guess, exceeding what the database can actually
   support well even before hitting the hard connection limit.

## Diagnose
- Check `pg_stat_activity` for the actual count and state of current
  connections (`active`, `idle`, `idle in transaction`) -- a large number
  of `idle in transaction` connections strongly suggests a leak or
  abandoned transaction, not genuine concurrent load.
- Compare total possible connections (app instances × configured pool
  size) against Postgres's `max_connections` to check for a simple
  capacity mismatch.
- For a suspected leak, check application code for connection/transaction
  acquisition that isn't wrapped in a guaranteed-release pattern
  (try/finally, a context manager, or the framework's equivalent) on
  every code path, including exception paths.
- Check whether a connection pooler (PgBouncer, RDS Proxy, etc.) sits
  between the application and Postgres, and its own pool size/mode
  (session vs. transaction pooling) relative to actual concurrency.

## Fix
- For a genuine capacity mismatch, introduce (or resize) a connection
  pooler between application instances and Postgres, since a pooler in
  transaction-pooling mode can serve many more logical application
  connections than direct Postgres connections would allow, rather than
  raising `max_connections` indefinitely (which has its own memory/
  performance cost per connection).
- For a leak, fix the specific code path that acquires without a
  guaranteed release -- wrap acquisition in a context manager/try-finally
  so a connection/transaction is always returned to the pool or rolled
  back, including on exceptions.
- For long-running/abandoned transactions, set a statement timeout
  and/or an idle-in-transaction timeout at the database or pooler level
  as a safety net, and separately fix the application code causing
  transactions to stay open longer than necessary (e.g. making an
  external API call while holding a database transaction open).
- Size the application's own pool based on actual concurrency needs and
  the database's real capacity, not an arbitrary large number "to be
  safe" -- a pool larger than the database can serve well doesn't help
  throughput and makes exhaustion happen at a less obvious threshold.

## Pitfalls
- Raising `max_connections` as a first response treats the symptom, not
  the cause, and each additional connection has real memory overhead on
  the Postgres side -- diagnose leak-vs-capacity first (via
  `pg_stat_activity`) before deciding this is even the right lever.
- A connection pooler in the wrong mode (session pooling instead of
  transaction pooling) for a workload of many short transactions doesn't
  provide the connection-multiplexing benefit that made adding it
  worthwhile -- confirm the pooling mode actually matches the workload's
  transaction pattern.

## Verify
After the fix, monitor `pg_stat_activity`'s connection count and state
distribution under realistic load and confirm the `idle in transaction`
count stays low and total connections stay comfortably under the
configured limit, including during a load test that previously triggered
the exhaustion.
