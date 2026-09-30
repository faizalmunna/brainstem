---
name: asyncio-lock-reentrant-deadlock
description: An async program using asyncio.Lock hangs forever the moment a code path tries to acquire the same lock it already holds.
triggers: ["asyncio lock deadlock", "await lock.acquire hangs", "async with lock never returns", "nested lock acquisition hangs", "asyncio lock not reentrant"]
permissions: ["READ"]
---

## Symptom
A coroutine that holds an `asyncio.Lock` (typically via `async with
lock:`) calls -- directly or through several layers of function calls --
another coroutine that tries to acquire the *same* lock again before the
first `async with` block exits. The program doesn't crash; it just hangs
indefinitely at the second `acquire()`, with no exception, no timeout,
and no obvious stack trace pointing at the problem.

## Likely causes
1. **A direct re-entrant call**: a method that acquires the lock calls
   another method on the same object that also acquires the lock, and
   both are invoked on the same call stack within one logical operation
   (e.g. a public method takes the lock, then calls a "helper" method
   that also takes it, not realizing it's already held).
2. **An indirect cycle through callbacks or event handlers**: code inside
   a locked section triggers a callback (a done-callback, a signal
   handler, an event emitter) that itself, several frames away, ends up
   calling back into a function that acquires the same lock -- harder to
   spot than a direct call because the reentrance isn't visible from
   reading either function alone.
3. **`asyncio.Lock` mistaken for `threading.RLock` semantics.** Unlike
   `threading.RLock`, `asyncio.Lock` has no concept of "owner" and is not
   reentrant -- there is no built-in count that lets the same logical
   owner acquire it twice and release it twice safely. Code ported from
   threading code that used `RLock`, or written by someone assuming locks
   are reentrant by default, deadlocks the first time the assumption is
   tested.

## Diagnose
- Confirm it's a deadlock, not just slowness: the hang doesn't resolve on
  its own even after a long wait, and adding a print immediately before
  the second `acquire()` shows it's reached but never returns.
- Dump the running tasks with `asyncio.all_tasks()` and inspect each
  task's stack (`task.get_stack()` or `task.print_stack()`); the task
  waiting on the second acquire will show its call chain, which usually
  reveals the earlier frame (in the same task) that already holds the
  lock -- this distinguishes a same-task reentrance from a genuine
  two-task contention issue.
- Add a short `asyncio.wait_for(lock.acquire(), timeout=2)` around the
  suspect acquisition temporarily; if it times out consistently at the
  same call site while other lock users proceed fine, that call site is
  the reentrant one.

## Fix
Restructure so the lock is only ever acquired once per logical
operation: have the public, lock-acquiring method call an internal
"already locked" version of the helper that assumes the lock is held and
never acquires it itself, rather than having both the outer and inner
methods each independently do `async with lock:`. If the two call paths
genuinely need independent entry points (sometimes called with the lock
held, sometimes not), have the inner function accept the lock's "held"
state as an explicit parameter or split into `_locked` and public
variants, rather than trying to detect reentrance implicitly.

```python
class Cache:
    def __init__(self):
        self._lock = asyncio.Lock()

    async def get_or_load(self, key):
        async with self._lock:
            return await self._get_or_load_locked(key)

    async def _get_or_load_locked(self, key):
        # assumes the lock is already held; never acquires it itself
        ...
```

## Pitfalls
- Reaching for a bigger hammer -- wrapping the whole call chain in
  `asyncio.wait_for` so it at least raises `TimeoutError` instead of
  hanging forever -- treats the symptom, not the cause; the underlying
  double-acquisition still means the second logical operation never
  actually ran, so downstream state can be left half-updated.
- Some codebases implement a custom "reentrant asyncio lock" by tracking
  the current task and letting it re-acquire freely; this is workable
  but easy to get subtly wrong across `await` boundaries (a task's
  identity can be ambiguous inside nested `TaskGroup`s or when work is
  handed to another task) -- prefer restructuring to avoid the
  reentrance over building custom reentrant-lock logic unless the
  cross-task semantics are fully understood.

## Verify
Write a regression test that calls the public method in a scenario that
previously triggered the nested acquisition (e.g. a cache-miss path that
recursively calls the loader), wrap the test in
`asyncio.wait_for(..., timeout=5)`, and confirm it completes well within
the timeout instead of hanging -- then confirm concurrent calls from two
different tasks still serialize correctly (the second one's body doesn't
start until the first's lock-protected section finishes).
