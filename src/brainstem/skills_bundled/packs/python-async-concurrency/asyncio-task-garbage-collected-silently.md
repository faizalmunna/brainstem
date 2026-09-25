---
name: asyncio-task-garbage-collected-silently
description: A fire-and-forget asyncio.create_task() coroutine stops partway through and never completes, with no exception or log to explain why.
triggers: ["task disappeared", "create_task never finishes", "background task stopped silently", "asyncio task garbage collected", "fire and forget task not running"]
permissions: ["READ"]
---

## Symptom
A coroutine started with `asyncio.create_task(...)` and not otherwise
awaited runs for a while -- sometimes logging a line or two -- and then
simply stops. No exception is raised, nothing appears in logs about
cancellation, and the calling code never checks on it again because it
was meant to run "in the background." The task just evaporates partway
through its work.

## Likely causes
1. **No strong reference to the task was kept.** `asyncio.create_task()`
   returns a `Task` object, and the event loop only holds a *weak*
   reference to tasks it's running. If the only reference was a local
   variable that goes out of scope (e.g. `asyncio.create_task(worker())`
   called as a bare expression, or assigned to a variable inside a
   function that then returns), the task object can be garbage collected
   before it finishes, and CPython's GC silently cancels/drops it.
2. **The task was assigned to a variable that got reused or overwritten**
   in a loop -- e.g. `t = asyncio.create_task(handle(item))` inside a
   `for` loop with no collection to hold each `t`, so only the last
   iteration's task survives GC pressure and earlier ones are collected
   mid-flight.
3. **The task's parent coroutine/function returned or was itself
   cancelled**, and whatever container held the task reference was
   local to that scope, so the task became unreachable even though the
   programmer's intent was for it to keep running independently.

## Diagnose
- Grep for `asyncio.create_task(` and `loop.create_task(` call sites and
  check, for each one, whether the returned object is stored anywhere
  that outlives the current function call (a module-level set, an
  object attribute, a task-tracking registry) -- not just a local
  variable that's never read again.
- Reproduce with `PYTHONASYNCIODEBUG=1` and add a
  `weakref.finalize(task, lambda: print("task GC'd", task))` on a
  suspect task in a test harness -- if the finalizer fires before the
  coroutine logically finished, that confirms GC is the culprit rather
  than a silent exception.
- Check whether the task's exception was ever retrieved: an
  unreferenced, GC'd task with a pending exception logs "Task exception
  was never retrieved" to the `asyncio` logger at GC time -- search logs
  for that exact message, since it's the strongest direct evidence.

## Fix
Keep a strong reference to every fire-and-forget task for its entire
lifetime, and have something responsible for eventually reaping it. The
common pattern: maintain a module- or object-level `set` of in-flight
tasks, add each new task to it immediately, and register a
`task.add_done_callback(background_tasks.discard)` so completed tasks
are removed automatically without needing to be awaited individually.
This gives the task a reference that survives until it's done, without
requiring the caller to block on it.

```python
_background_tasks: set[asyncio.Task] = set()

def spawn(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
```

## Pitfalls
- Storing tasks in a list and never removing finished ones "fixes" the
  GC problem but creates an unbounded memory leak over a long-running
  process -- always pair the registry with a done-callback that removes
  the entry, as above.
- Adding a strong reference stops premature GC but does nothing about
  swallowed exceptions -- a task that raises and is never awaited still
  only surfaces its exception via the "exception was never retrieved"
  log line at GC time unless the done-callback also checks
  `task.exception()` and handles/logs it explicitly.

## Verify
Write a test that creates several fire-and-forget tasks via the fixed
`spawn()` helper, forces a full GC pass (`gc.collect()`) while they're
still mid-`await asyncio.sleep(...)`, and asserts each one still
completes and its side effect (e.g. an appended result, a written file)
is observed -- confirming the task survives collection instead of being
silently dropped.
