---
name: asyncio-cancellation-swallowed-by-broad-except
description: Calling task.cancel() has no visible effect because a broad exception handler inside the coroutine catches and discards the resulting CancelledError.
triggers: ["task.cancel() does nothing", "coroutine keeps running after cancel", "cancellederror caught by except exception", "asyncio task wont stop", "cancel not stopping task"]
permissions: ["READ"]
---

## Symptom
`task.cancel()` is called on a running task, expecting it to stop at its
next `await` point, but the task keeps running as if nothing happened --
no `CancelledError` is ever observed by the caller, `task.cancelled()`
returns `False` after the task eventually finishes normally, and there's
no error output suggesting anything went wrong internally.

## Likely causes
1. **A broad `except:` or `except Exception:` inside the coroutine sits
   around an `await` point and catches the `CancelledError` raised
   there.** In Python 3.8+, `asyncio.CancelledError` inherits from
   `BaseException`, not `Exception`, so a plain `except Exception:`
   should *not* catch it -- but a bare `except:` (no exception class at
   all), or an explicit `except BaseException:`, or code originally
   written for Python 2/older asyncio conventions (where
   `CancelledError` was `Exception`-derived), still swallows it
   silently.
2. **The exception is caught correctly but not re-raised.** Even code
   using `except asyncio.CancelledError:` deliberately (e.g. to run
   cleanup) sometimes forgets to `raise` at the end of that block --
   catching a `CancelledError` to do cleanup and then *not* propagating
   it leaves the task believing it completed normally, and the caller
   awaiting it never sees the cancellation at all.
3. **The task is retried or wrapped in a loop that catches all
   exceptions to retry the operation**, treating `CancelledError` as
   just another transient failure to retry rather than a shutdown
   signal -- a `while True: try: await work() except Exception: continue`
   pattern (if it happens to also catch `BaseException`, or the retry
   logic is layered above code that already swallowed it) causes the
   task to keep re-running the same work indefinitely, immune to
   cancellation.

## Diagnose
- Grep the coroutine (and everything it calls, including any retry
  wrappers) for `except:` with no class, `except BaseException:`, or
  `except (Exception, BaseException):`-style catches around any
  `await` -- these are the only ways `CancelledError` gets caught
  unintentionally in modern Python.
- For code that does deliberately catch `except asyncio.CancelledError:`,
  check whether every branch of that handler ends in `raise` (or
  re-raises the caught exception) -- a handler that logs and falls
  through without re-raising silently absorbs the cancellation.
- Add a targeted test: call `task.cancel()` on the suspect coroutine
  running in an event loop, `await` the task inside
  `pytest.raises(asyncio.CancelledError)` (or an equivalent
  try/except asserting the exception type), and confirm whether it's
  actually raised back to the awaiter -- if the test's `await task`
  returns normally instead of raising, cancellation is confirmed
  swallowed somewhere in the chain.

## Fix
Never catch cancellation with an unqualified `except:` or
`except BaseException:` in coroutine code meant to remain cancellable.
Where cleanup on cancellation is genuinely needed, catch
`asyncio.CancelledError` specifically, do the cleanup, and always
re-raise:

```python
async def worker():
    try:
        while True:
            await do_unit_of_work()
    except asyncio.CancelledError:
        await release_resources()
        raise   # mandatory -- lets the cancellation actually propagate
```

For retry loops, explicitly exclude `CancelledError` from what gets
retried, either by catching `Exception` only (never
`BaseException`) or by adding an explicit
`except asyncio.CancelledError: raise` above the broader retry
`except Exception:` clause so it's handled first and never reaches the
retry logic.

## Pitfalls
- "Fixing" this by wrapping the whole coroutine in
  `except asyncio.CancelledError: pass` (catch and drop, no re-raise)
  stops the exception from propagating to callers but does not actually
  make the task's cancellation semantics correct -- `task.cancelled()`
  will still report `False`, and any code relying on that flag (or on
  awaiting the task and expecting `CancelledError`) will behave as if
  nothing was ever cancelled.
- Adding cleanup logic inside the `except CancelledError:` block that
  itself `await`s something can raise a *second* `CancelledError`
  during that cleanup `await` (since the task is already being
  cancelled) -- if that cleanup needs to run to completion regardless,
  shield it explicitly (e.g. run the essential cleanup step wrapped so
  it isn't itself interrupted) rather than assuming the cleanup await
  is safe just because it's inside the handler.

## Verify
Re-run the targeted cancellation test: call `task.cancel()`, await the
task, and confirm `asyncio.CancelledError` is now actually raised to the
awaiter and `task.cancelled()` returns `True` -- then confirm any
cleanup expected on cancellation (a released lock, a closed connection)
actually happened by checking its post-cancellation state directly.
