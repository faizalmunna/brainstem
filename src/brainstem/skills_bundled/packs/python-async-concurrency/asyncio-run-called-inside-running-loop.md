---
name: asyncio-run-called-inside-running-loop
description: Calling asyncio.run() or loop.run_until_complete() raises RuntimeError because it's invoked from code that's already executing inside a running event loop.
triggers: ["asyncio.run cannot be called from a running event loop", "runtimeerror this event loop is already running", "nested asyncio.run error", "jupyter asyncio.run fails", "asyncio.run inside async function"]
permissions: ["READ"]
---

## Symptom
Calling `asyncio.run(coro())` (or `loop.run_until_complete(coro())`)
raises `RuntimeError: asyncio.run() cannot be called from a running
event loop` (or the older `RuntimeError: This event loop is already
running`). This often appears confusing because the calling code "looks"
synchronous at the call site -- it's not obviously inside an `async def`
-- yet the error insists a loop is already running.

## Likely causes
1. **`asyncio.run()` is called from inside code that's already running
   under an event loop somewhere up the call stack** -- most commonly, a
   library function does `asyncio.run(fetch())` internally as a
   convenience "just run this async thing synchronously" helper, and
   that function gets called from *within* an application that's itself
   async (a web framework request handler, another coroutine) -- the
   library's assumption that it's always the outermost caller breaks the
   moment it's used from async application code.
2. **Running in an environment that already manages its own event loop**
   -- Jupyter/IPython notebooks, some GUI frameworks, and certain test
   runners (`pytest-asyncio` in some configurations) start and hold a
   running loop for the whole session/test, so any code that also calls
   `asyncio.run()` at the top level collides with that already-running
   loop instead of getting a fresh one.
3. **Mixing sync and async entry points across a codebase migration** --
   code partially converted to async still has some call sites that
   assume they're the synchronous entry point and wrap their one async
   call in `asyncio.run(...)`, but callers upstream have since become
   async themselves and now call that "sync-looking" function from
   inside a coroutine, triggering the nested-loop error at the seam
   between old and new code.

## Diagnose
- Read the full traceback, not just the error message: it shows exactly
  which frame called `asyncio.run()` (or `run_until_complete`) and which
  frame above it is already inside a coroutine/event loop -- that upper
  frame is the actual caller responsible for choosing how to run async
  code correctly, not the frame where the error was raised.
- Check `asyncio.get_event_loop().is_running()` (or, in newer code,
  attempt `asyncio.get_running_loop()` in a try/except) at the point
  right before the failing call, in a debugger or with a temporary log
  line, to confirm a loop is indeed already active there rather than the
  error being something else entirely.
- If the failure is intermittent (works standalone, fails inside a
  notebook or under a particular test runner), check whether that
  specific environment pre-starts an event loop -- Jupyter's IPython
  kernel and some `pytest-asyncio` fixture modes do this, which explains
  why identical code fails only in that context.

## Fix
There should be exactly one place in the whole call stack that starts
the event loop -- normally the true top-level entry point of the
program (`if __name__ == "__main__": asyncio.run(main())`). Any function
that might be called from either sync or async contexts should be
`async def` itself and simply `await` the work, letting its caller
decide how to run it, rather than calling `asyncio.run()` internally.
For a function that genuinely needs to offer a synchronous API while
doing async work underneath, detect whether a loop is already running
and branch:

```python
def run_sync_or_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)          # no loop running: safe to start one
    else:
        raise RuntimeError(
            "already inside an event loop; await the coroutine directly instead"
        )
```

In Jupyter/IPython specifically, either `await` the coroutine directly
at the top level (supported there) instead of calling `asyncio.run()`,
or use a library designed for nested loops (e.g. `nest_asyncio`) only as
a deliberate, documented workaround -- not a default habit.

## Pitfalls
- Reaching for `nest_asyncio.apply()` everywhere a nested-loop error
  appears "fixes" the symptom by patching asyncio to tolerate reentrant
  loops, but papers over an underlying design problem (a function that
  shouldn't assume it owns the loop) and can mask real bugs in code that
  should instead be refactored to be properly async end-to-end.
- Converting the inner function to `async def` and having it call
  `asyncio.run()` on *itself* to "make it work either way" is
  self-contradictory -- an `async def` function is already a coroutine;
  wrapping its own body in `asyncio.run()` doesn't make sense and
  usually signals the sync/async boundary wasn't actually resolved, just
  moved.

## Verify
Call the fixed function from both a plain synchronous script (confirm it
still runs to completion via its own `asyncio.run()`) and from inside an
existing coroutine in an async test (confirm it's now `await`ed
directly with no nested-loop error) -- both call paths succeeding
confirms the sync/async boundary is resolved rather than only fixed for
whichever context was tested first.
