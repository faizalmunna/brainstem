---
name: connection-pool-exhausted-on-error-path
description: Diagnose an Express app whose database connection pool runs out of connections specifically after a burst of failed or erroring requests.
triggers: ["pool exhausted node", "timeout acquiring connection from pool", "connections not released on error", "too many connections error under load", "db pool empty after errors"]
permissions: ["READ"]
---

## Symptom
The app works normally under regular traffic but starts failing with a
pool-timeout error (e.g. `TimeoutError: ResourceRequest timed out`,
`Error: Timeout acquiring a connection`, or the driver's equivalent)
specifically after a period where requests were erroring out -- a
downstream dependency blip, a spike of invalid input, a bug in one
endpoint -- even though the request *rate* wasn't unusually high. The
pool appears to just never get connections back.

## Likely causes
1. **A connection or client checked out from the pool isn't released in
   the `catch` branch** -- code that does
   `const conn = await pool.getConnection(); ...query...;
   conn.release();` releases correctly on success but throws before
   reaching `conn.release()` when the query itself fails, permanently
   leaking that connection.
2. **A transaction started but never rolled back or committed on an
   error path** -- `BEGIN` issued, an error occurs mid-transaction, and
   the code returns/throws without calling `ROLLBACK`, leaving the
   connection in an unusable transactional state even if it's technically
   "released" back to the pool.
3. **An ORM/driver's connection is held across an `await` that can
   reject** in a code path structured so the `finally`/release logic is
   attached to the wrong scope -- e.g. release logic inside a `.then()`
   chain that a thrown error skips entirely, rather than in a `finally`
   block that always runs.
4. **Retried requests each acquiring a new connection without the
   previous one being released first** -- a retry wrapper that catches an
   error and calls the same function again without confirming the prior
   attempt's connection was returned to the pool.

## Diagnose
- Check the pool's live stats if the driver exposes them (many do:
  total/idle/waiting counts) before and during the failure window --
  a total count near the pool's configured max with near-zero idle
  connections, growing during a period of request errors, points
  directly at leaked acquisitions rather than genuine load.
- Grep every `pool.getConnection()`/`pool.connect()` (or ORM equivalent)
  call site for whether the matching release/`client.release()`/
  `connection.end()` call is inside a `finally` block -- if it's only in
  the code path after a successful query, that's the leak.
- Reproduce directly: force the specific failing query/endpoint to error
  repeatedly (bad input, a killed downstream dependency) in a test
  environment while watching the pool's idle-connection count -- it
  should return to baseline after each failed request; if it monotonically
  decreases, that confirms the leak and identifies which endpoint causes
  it.
- For transaction-specific leaks, check whether a `ROLLBACK` is issued on
  every code path out of a `BEGIN`/`COMMIT` block, including early
  returns and validation failures that occur after the transaction has
  already started.

## Fix
- Wrap every connection acquisition in a `try/finally` (not just
  `try/catch`) so release happens unconditionally:
  `const conn = await pool.getConnection(); try { ... } finally {
  conn.release(); }` -- `finally` runs whether the block completes,
  throws, or returns early, which a `catch`-only or success-path-only
  release does not guarantee.
- For transactions, wrap the whole sequence so a failure triggers
  `ROLLBACK` before the connection is released: `try { await
  conn.query('BEGIN'); ...; await conn.query('COMMIT'); } catch (err) {
  await conn.query('ROLLBACK'); throw err; } finally { conn.release();
  }` -- rollback must happen before release, since releasing a connection
  still mid-transaction back to the pool corrupts it for whoever acquires
  it next.
- Where the framework/ORM supports it, prefer a scoped helper
  (`pool.withConnection(async conn => {...})`,
  `sequelize.transaction(async t => {...})`) that guarantees
  acquire/release or begin/commit/rollback pairing internally, so
  individual call sites can't get the pairing wrong.
- Set a pool acquire timeout (most drivers support one) so a leak
  degrades into visible, fast-failing timeout errors rather than an
  unbounded hang -- this doesn't fix the leak but makes it fail loudly
  and quickly instead of quietly starving the pool over time.

## Pitfalls
- Increasing the pool's max size in response to exhaustion treats the
  symptom, not the leak -- it buys time before the same leak exhausts the
  larger pool too, and can make the underlying database's own max
  connection limit the next failure point instead.
- Releasing a connection in `finally` but forgetting to `ROLLBACK` first
  on a transaction failure returns a connection to the pool that's still
  inside an open transaction -- the next request to acquire it inherits
  uncommitted state or gets confusing "transaction already in progress"
  errors that look unrelated to pooling at first glance.
- Wrapping acquisition in `try/finally` but calling `conn.release()`
  with an argument some pool implementations interpret as "destroy this
  connection instead of returning it healthy" (check the driver's
  specific API) can silently shrink the effective pool size over time
  even though every acquisition is technically being "released."

## Verify
Force the specific error path identified in diagnosis to fail repeatedly
(e.g. 50 consecutive requests against a query designed to throw) and
confirm the pool's idle/available connection count returns to baseline
after each one rather than trending toward zero, then confirm a
subsequent burst of normal successful requests still succeeds without
hitting the acquire timeout.
