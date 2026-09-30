---
name: sync-function-disguised-as-async-blocks-gather
description: An asyncio.gather() call meant to run several requests concurrently instead completes in the same total time as running them one after another.
triggers: ["asyncio gather not concurrent", "gather running sequentially", "async functions not actually parallel", "await gather same speed as loop", "concurrent requests still slow"]
permissions: ["READ"]
---

## Symptom
Code wraps several calls in `asyncio.gather(*coros)` expecting them to
run concurrently and finish in roughly the time of the *slowest* one, but
measured wall-clock time instead looks like the *sum* of all of their
individual durations -- as if `gather` were just calling them one after
another.

## Likely causes
1. **The "async" functions are `async def` but contain no real `await`
   on I/O** -- they use a blocking library internally (`requests.get`,
   a synchronous DB driver, `time.sleep`) while still being declared
   `async def`. Being declared `async def` does not make a function
   concurrent; it only makes it awaitable. If it never hits a real
   `await` that yields to the event loop, it runs to completion before
   any other task gets a turn, exactly like a synchronous call would.
2. **A supposedly-async client library that blocks internally** for part
   of its work (blocking DNS resolution, a blocking connection-pool
   checkout) even though its public API is `async def` and it does
   `await` other things -- the concurrency gap is smaller but still real
   and easy to miss because the code "looks" async throughout.
3. **The coroutines were awaited individually before being passed to
   `gather`** -- e.g. `results = [await f() for f in coros]` instead of
   `results = await asyncio.gather(*(f() for f in coros))` -- which
   defeats concurrency entirely regardless of how well-behaved the
   coroutines are, since each `await` in the list comprehension fully
   completes before the next one starts.

## Diagnose
- Read every function passed into `gather` and check whether it makes
  at least one `await` on something that actually yields control (an
  async HTTP client call, `await asyncio.sleep`, an async DB query) --
  not just whether the function is declared with `async def`.
- Add a timestamp print/log at entry and exit of each coroutine and run
  them through `gather`: if entries are staggered but interleaved
  (task B starts before task A finishes), it's genuinely concurrent; if
  each one's exit timestamp precedes the next one's entry timestamp,
  they ran sequentially despite `gather`.
- Search the call site for `await` inside a loop or comprehension that
  builds the list passed to `gather` -- confirm the coroutines are
  created (called but not awaited) first and only awaited collectively
  by `gather`, e.g. `asyncio.gather(f(), g(), h())`, not
  `[await f(), await g()]`.

## Fix
Ensure every "concurrent" branch does real, yielding I/O: swap blocking
calls for their async-native equivalents (an async HTTP client instead
of `requests`, an async DB driver, `await asyncio.sleep` instead of
`time.sleep`). Where a genuinely blocking call has no async equivalent,
offload it with `asyncio.to_thread(...)` so it runs on a worker thread
and the coroutine's `await` on that call actually yields to the loop,
letting `gather` interleave it with the others. Then pass all coroutine
*objects* into a single `gather` call rather than awaiting them one at a
time:

```python
async def fetch(url):
    async with session.get(url) as resp:   # real yield point
        return await resp.text()

results = await asyncio.gather(*(fetch(u) for u in urls))
```

## Pitfalls
- Wrapping a blocking call in `asyncio.to_thread` restores concurrency
  for I/O-bound work but does nothing for CPU-bound work -- threads still
  contend for the GIL, so "concurrent" CPU-heavy tasks offloaded this way
  will overlap in wall-clock time but not actually go faster in
  aggregate; that requires a process pool instead.
- Mixing one still-blocking coroutine into an otherwise-fixed `gather`
  call reintroduces the same serialization for every task queued behind
  it on the event loop, not just for itself -- audit every coroutine in
  the batch, not just the ones suspected first.

## Verify
Instrument each coroutine to record its start and end monotonic
timestamps into a shared list, run the fixed `gather` call, and assert
that the time ranges overlap (any coroutine's start time is before
another's end time) -- and that total wall-clock time is close to the
slowest single call, not the sum of all calls.
