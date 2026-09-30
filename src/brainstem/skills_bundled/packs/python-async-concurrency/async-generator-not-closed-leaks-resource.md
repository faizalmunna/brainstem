---
name: async-generator-not-closed-leaks-resource
description: A resource opened inside an async generator (a DB cursor, file handle, or connection) stays open long after the code iterating it stopped, leaking connections over time.
triggers: ["async generator resource leak", "connection not closed after async for", "async generator finally never runs", "aclosing needed", "db cursor leaking after break"]
permissions: ["READ"]
---

## Symptom
An async generator function opens a resource (a database cursor, an
open file, a network connection) at the top and releases it in a
`finally` block below a `yield`, expecting the `finally` to run when
iteration ends. In practice, some code paths that consume the generator
leave the resource open indefinitely -- connection pools slowly exhaust,
file descriptor counts climb, and nothing in the logs points at the
generator as the source because the leak accumulates gradually across
many calls rather than failing loudly on any single one.

## Likely causes
1. **The consumer stops iterating early without closing the generator**
   -- a `break` inside `async for item in gen():`, a `return` in the
   middle of the loop body, or an exception that propagates out of the
   loop all abandon the generator without ever resuming it to the point
   where its `finally` block executes. Unlike a `with` block, exiting an
   `async for` loop early does **not** automatically call `aclose()` on
   the generator being iterated.
2. **The generator is passed around and partially consumed by different
   layers of code** (e.g. one function gets the first N items and hands
   the rest off, or a generator is stored and iterated across multiple
   request handlers), so no single piece of code has clear ownership
   responsible for closing it when the caller is done.
3. **`GeneratorExit` is caught and suppressed inside the generator**,
   often unintentionally via a broad `except Exception:` around the
   yield, which prevents `aclose()` from actually finishing the
   generator's cleanup -- the caller may believe it closed the resource,
   but the generator's `finally` never completes because the
   `GeneratorExit` used to drive it there was swallowed.

## Diagnose
- Grep for async generator functions (`async def ...` containing
  `yield`) that acquire a resource before the `yield` and release it in
  a `finally` after -- then check every call site that iterates them for
  a `break`, early `return`, or an exception-handling path inside the
  loop body.
- Reproduce with a resource that logs on open/close (wrap the real
  resource in a thin logging proxy in a test), iterate the generator but
  `break` after the first item, and check whether the close log line
  ever appears -- if not, that confirms the leak path.
- For a connection-pool-based leak, watch the pool's in-use/checked-out
  connection count over repeated calls that break early; a count that
  only grows and never returns to baseline between calls is the
  detectable signature, distinct from a pool simply being undersized.

## Fix
Use `contextlib.aclosing()` (or an explicit `try/finally` calling
`await gen.aclose()`) around any async generator that owns a resource,
so cleanup runs even if the loop body exits early via `break`, `return`,
or an exception -- mirroring how `with` guarantees cleanup for context
managers.

```python
from contextlib import aclosing

async def rows_from(query):
    conn = await pool.acquire()
    try:
        cursor = await conn.cursor(query)
        async for row in cursor:
            yield row
    finally:
        await pool.release(conn)

async def handle():
    async with aclosing(rows_from(query)) as gen:
        async for row in gen:
            if should_stop(row):
                break   # aclosing() still closes gen on exit
```

For generators handed across layers/ownership boundaries, make explicit
which layer owns the close call, or wrap the hand-off itself in
`aclosing` at the outermost point that has authority to end iteration.

## Pitfalls
- Wrapping the resource acquisition in `try/finally` inside the
  generator is necessary but not sufficient -- without `aclosing()` (or
  an explicit `aclose()` call) at the *consumer* side, an early `break`
  still never triggers that `finally`, since nothing resumes the
  generator to run it.
- Catching `GeneratorExit` inside the generator body to do extra
  cleanup is fine, but re-raising it (or not swallowing it) is
  mandatory -- silently absorbing `GeneratorExit` breaks `aclose()`'s
  contract and can make Python emit a `RuntimeError: async generator
  ignored GeneratorExit` at a confusing, seemingly unrelated point later.

## Verify
Re-run the logging-proxy test from the diagnose step: iterate the
generator inside `aclosing()`, `break` after the first item, and confirm
the close log line now appears immediately after the `break` rather than
never -- then run a batch of many such early-break calls in a loop and
confirm the connection pool's in-use count returns to baseline between
calls instead of climbing.
