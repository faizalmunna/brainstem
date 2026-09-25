---
name: wait-for-timeout-leaves-task-running
description: Code that catches a TimeoutError from asyncio.wait_for moves on, but the coroutine it timed out on keeps executing in the background and later causes duplicate effects.
triggers: ["wait_for timeout but task still running", "duplicate write after timeout", "asyncio.timeouterror task not cancelled", "background task keeps running after timeout", "wait_for side effect happens twice"]
permissions: ["READ"]
---

## Symptom
Code wraps a coroutine in `asyncio.wait_for(coro, timeout=N)`, catches
the resulting `TimeoutError`, logs it, and proceeds as if the operation
was abandoned. Later, a side effect from that "abandoned" operation
shows up anyway -- a duplicate database write, a second email sent, a
log line from code that should no longer be running -- because the
underlying work was still executing in the background after the
`wait_for` call returned.

## Likely causes
1. **Passing a bare coroutine (not a `Task`) to `wait_for` on a Python
   version/usage pattern where cancellation doesn't propagate as
   expected**, or the coroutine catches and suppresses
   `asyncio.CancelledError` internally (e.g. a broad
   `except Exception:` around its body, or in older code, `except
   BaseException:`) -- `wait_for` does cancel the underlying task on
   timeout, but if the coroutine swallows the resulting
   `CancelledError` instead of letting it propagate, the coroutine
   keeps running to completion despite the timeout having "fired."
2. **The awaited coroutine calls something that doesn't check for
   cancellation at all** -- a long synchronous/blocking call inside it
   (see the CPU-bound event-loop skill in this pack), or a call into a
   thread via `asyncio.to_thread` -- since cancelling the `asyncio.Task`
   wrapper does not, by itself, stop a plain OS thread already running
   the blocking call; the thread runs to completion regardless of the
   `Task` being marked cancelled.
3. **The code assumes `TimeoutError` means "nothing happened"** and
   doesn't account for a race where the operation actually succeeded
   (e.g. the write committed) microseconds before the cancellation
   reached it -- `wait_for` timing out only means the *caller* stopped
   waiting, not that the callee's side effect didn't or won't still
   land.

## Diagnose
- Add logging at the very start and very end of the wrapped coroutine
  (entry and exit/side-effect points), trigger a timeout deliberately
  (e.g. temporarily lower the timeout below the call's real duration),
  and check whether the "exit" log line appears *after* the caller has
  already logged the `TimeoutError` -- if so, the task is confirmed to
  outlive the timeout.
- Check whether the timed-out coroutine (or anything it calls) has a
  broad `except Exception` or `except BaseException` around an `await`
  point -- `CancelledError` inherits from `BaseException` in modern
  Python, so `except Exception` alone does not accidentally swallow it,
  but `except BaseException` (or a bare `except:`) will, and older code
  or ported threading code sometimes does this.
- If the wrapped call includes `asyncio.to_thread` or
  `run_in_executor`, confirm directly: cancelling an `asyncio.Task`
  that's awaiting a thread-pool future does not stop the OS thread
  executing underneath it -- check whether the side effect originates
  from inside that thread specifically, which explains why cancellation
  "didn't work" even though the async-level cancellation itself was
  correct.

## Fix
Treat the cancelled task as something that needs explicit follow-up, not
something `wait_for` fully cleans up on its own for you. Wrap the
`wait_for` call to also await the cancelled task's actual termination and
handle idempotency at the effect layer:

```python
task = asyncio.ensure_future(do_work())
try:
    return await asyncio.wait_for(asyncio.shield(task), timeout=5)
except asyncio.TimeoutError:
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task   # ensure it actually stops before returning
    raise
```

Design the underlying operation to be safely cancellable (checkpoints
that check `asyncio.current_task().cancelled()` are unnecessary --
letting `CancelledError` propagate naturally through `await` points is
enough) and, where the side effect can't be made instantly cancellable
(a thread doing a blocking write), make the side effect itself
idempotent so a completed-after-timeout write doesn't duplicate an
already-applied one.

## Pitfalls
- `asyncio.shield()` protects a task from being cancelled *by the
  `wait_for` wrapping it*, which is useful when you want the work to
  keep running even after the caller stops waiting -- but it's easy to
  reach for reflexively and end up back at the original bug (a task that
  outlives the timeout) if the intent was actually to stop the work, not
  just stop waiting for it.
- Cancelling a task and immediately moving on without awaiting it
  (skipping the `await task` after `task.cancel()`) means the caller
  can't distinguish "cancellation completed cleanly" from "cancellation
  request was swallowed and the task is still running" -- always await
  the cancelled task (suppressing the expected `CancelledError`) to
  confirm it actually stopped.

## Verify
Deliberately trigger a timeout against a test double that records
whether its cleanup/side-effect code ran, confirm the caller's
`except TimeoutError` branch only proceeds after the awaited,
cancelled task has actually finished (no further log lines/side effects
appear after the caller resumes), and confirm the test double's side
effect was not applied twice when the timeout is set lower than the
call's natural duration.
