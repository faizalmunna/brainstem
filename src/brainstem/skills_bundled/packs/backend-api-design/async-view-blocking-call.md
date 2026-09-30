---
name: async-view-blocking-call
description: Diagnose an async FastAPI/Node/Django-async service that stops handling concurrent requests because a handler makes a blocking synchronous call.
triggers: ["async endpoint blocks", "throughput dropped after adding async", "event loop blocked", "fastapi slow under load", "one slow request blocks all requests"]
permissions: ["READ"]
---

## Symptom
An async web service (FastAPI, async Django views, Node/Express) that
should handle many concurrent requests on one event loop instead sees
throughput collapse under load -- one slow request appears to block or
slow down *all other* concurrent requests, not just the one making the
slow call.

## Likely causes
1. **A blocking (synchronous) call made directly inside an `async def`
   handler** -- a synchronous DB driver call, a synchronous HTTP client
   (e.g. `requests.get` instead of an async client), `time.sleep`
   instead of `await asyncio.sleep`, or CPU-bound work (image processing,
   large JSON parsing/serialization, cryptographic hashing) done inline.
2. **A "sync" ORM/driver used from async code** without routing it
   through a thread pool -- looks like it works in testing with light
   load, then serializes all requests under real concurrency because
   every one blocks the single event loop in turn.
3. **A supposedly-async third-party client that has a blocking code path**
   internally (e.g. blocking DNS resolution, blocking file I/O) not
   obvious from its async-looking API surface.

## Diagnose
- Identify what "blocks all other requests" actually means here: on a
  single-threaded event loop, any synchronous call that doesn't yield
  control back prevents *every* concurrently-awaiting request from
  progressing until it returns -- so the fix target is specifically
  "which line doesn't await/yield."
- Grep the suspect handler and everything it calls for synchronous I/O:
  standard blocking HTTP clients, blocking DB drivers, `time.sleep`,
  synchronous file reads, blocking subprocess calls.
- Under a load test, watch whether *all* concurrent request latencies
  spike together when one slow-path request is triggered, versus only
  the slow request itself being slow -- the former confirms event-loop
  blocking rather than a resource-contention issue elsewhere (e.g. a
  connection pool limit, which produces a different pattern).

## Fix
- Replace blocking calls with their async equivalents where a real async
  client/driver exists (async DB driver, async HTTP client, `await
  asyncio.sleep` instead of `time.sleep`).
- Where no async equivalent exists (a CPU-bound library, a legacy
  synchronous SDK), run the blocking call in a thread pool executor
  (`asyncio.to_thread` / `run_in_executor`, or the framework's built-in
  mechanism for offloading sync work) so it doesn't occupy the event
  loop thread while it runs.
- For genuinely CPU-bound work (not I/O-bound), consider a separate
  process pool or a background worker queue instead of a thread pool,
  since CPU-bound work in a thread still contends for the GIL in Python
  and doesn't parallelize the way I/O-bound thread offloading does.

## Pitfalls
- Wrapping a blocking call in `asyncio.to_thread` fixes the event-loop-
  blocking symptom but doesn't fix an underlying resource bottleneck
  (e.g. a connection pool sized for far fewer concurrent connections than
  the new concurrency level allows) -- check pool sizes after fixing the
  blocking call, since load can now actually reach them concurrently.
- Mixing sync and async database sessions/transactions in the same
  request (e.g. an async ORM call followed by a sync one against the same
  connection) can cause subtle transaction/connection-state bugs, not
  just a performance issue -- audit for consistency, not just presence of
  `await`.

## Verify
Run a load test with one artificially slow request mixed into a batch of
otherwise-fast concurrent requests, before and after the fix, and confirm
the fast requests' latency no longer spikes in lockstep with the slow
one after the blocking call is offloaded/made async.
