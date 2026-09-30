---
name: shared-mutable-state-race-without-lock-single-threaded-assumption
description: Multiple asyncio tasks reading and updating the same in-memory dict or counter produce corrupted or lost updates despite there being only one OS thread.
triggers: ["asyncio race condition single threaded", "lost update async tasks", "shared dict corrupted async", "asyncio thought it was safe no lock", "concurrent tasks overwriting each other"]
permissions: ["READ"]
---

## Symptom
Several `asyncio` tasks read, modify, and write back a shared in-memory
structure (a dict of counters, a cache, an account balance) with no
lock, on the reasoning that "asyncio is single-threaded so there's no
race condition." Under concurrency, updates still go missing, counters
end up lower than the number of increments performed, or a cache entry
is briefly seen in an inconsistent partially-updated state by another
task.

## Likely causes
1. **A read-modify-write sequence spans an `await` point.** Single-
   threaded execution guarantees no two tasks run Python bytecode at
   the *exact same instant*, but it does **not** guarantee no other task
   runs *between* two statements in the same task if there's an `await`
   between them. `value = shared[key]; await something(); shared[key] =
   value + 1` lets another task's coroutine run during the `await` and
   read/write `shared[key]` in between, producing a classic lost update
   -- the single-threaded guarantee only prevents true simultaneous
   execution, not interleaving.
2. **A compound operation assumed to be atomic isn't**, even with no
   explicit `await` written in the line itself -- e.g. `shared[key] +=
   1` where `shared` is a custom object whose `__setitem__`/`__iadd__`
   internally awaits something (a proxy object, a class wrapping a
   remote cache), so the `await` is hidden inside a method call that
   doesn't look, at the call site, like it yields control.
3. **Task-switching was introduced later by an unrelated change** -- code
   that was correct when the shared-state functions were purely
   synchronous becomes racy the moment any function in the call chain is
   changed to `await` something (e.g. adding a logging call that awaits
   an async logger, or adding a cache lookup), without anyone revisiting
   the original "this is safe, nothing here awaits" reasoning.

## Diagnose
- Find every read-modify-write sequence on shared mutable state and check
  specifically whether an `await` (of any kind, including ones hidden
  inside helper calls) occurs between the read and the write -- that gap
  is the exact race window, not "is this code technically running on
  multiple threads."
- Reproduce deterministically by inserting `await asyncio.sleep(0)` (a
  minimal yield) directly between the read and write in a test build,
  and launch many tasks performing the same increment concurrently via
  `asyncio.gather` -- a correct final count without the fix, and a
  wrong (lower) one with the artificial yield inserted, confirms the
  interleaving is the actual mechanism, not something more exotic.
- Log each task's read and write of the shared value with an
  interleavable identifier (task name and value seen) and inspect the
  log for a case where task B's write is based on a value read *before*
  task A's write that should have preceded it -- that's the lost-update
  pattern made visible.

## Fix
Protect every read-modify-write sequence that spans an `await` (directly
or through a hidden one) with an `asyncio.Lock`, exactly as you would
guard a critical section in threaded code -- the "single-threaded"
property only removes the need for OS-level primitives like
`threading.Lock`'s cross-core memory barriers, not the need for mutual
exclusion around interleaved logical operations:

```python
lock = asyncio.Lock()

async def increment(key):
    async with lock:
        shared[key] = shared.get(key, 0) + 1
        await maybe_flush_to_disk(key)   # await now safely inside the critical section
```

Where possible, restructure to avoid the `await` inside the critical
section entirely (do the async part before or after the lock-protected
mutation, keeping the mutation itself synchronous and instantaneous),
which shrinks the lock's hold time and reduces contention without
changing correctness.

## Pitfalls
- Adding a lock around the *read* and a separate lock around the *write*
  (two short critical sections instead of one spanning both) still
  leaves the same race window between them -- the lock must cover the
  entire read-modify-write span as one critical section, not each half
  independently.
- Over-applying locks to every shared-state access "just in case,"
  including ones with no `await` anywhere in the call chain, adds
  unnecessary contention and complexity for operations that were never
  actually at risk -- audit for an actual yield point between read and
  write before deciding a lock is needed there.

## Verify
Run the concurrent-increment test from the diagnose step (many tasks via
`asyncio.gather` incrementing the same key, with a real `await` inside
the protected section) after adding the lock, and confirm the final
count exactly equals the number of increments performed, run repeatedly
(e.g. 100 iterations) to rule out the race passing by chance rather than
being structurally fixed.
