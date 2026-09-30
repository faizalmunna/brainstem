---
name: event-loop-blocked-by-sync-cpu-work
description: Diagnose an Express server where one request doing heavy synchronous CPU work stalls every other concurrent request until it finishes.
triggers: ["express server freezes under load", "one request blocks all others", "JSON.parse blocking event loop", "server unresponsive during large payload processing", "node event loop 100% cpu one request"]
permissions: ["READ"]
---

## Symptom
An Express server that normally handles many concurrent connections fine
suddenly stops responding to *any* request -- health checks, static
assets, unrelated routes -- for several seconds or longer, and the pause
lines up exactly with one specific request (a large upload, a report
export, a signup with password hashing). Once that one request finishes,
every other queued request completes almost instantly, as if they'd been
paused rather than slow.

## Likely causes
1. **A large synchronous `JSON.parse`/`JSON.stringify`** on a big payload
   (a bulk import, a large response body) -- both are synchronous and
   proportional to input size, and neither yields to the event loop
   partway through.
2. **Synchronous cryptographic work** -- `crypto.pbkdf2Sync`,
   `bcrypt.hashSync`, synchronous signing/verification -- run directly in
   a route handler instead of the async/callback variant.
3. **A synchronous regex with catastrophic backtracking** on
   attacker- or user-controlled input, which can turn a normally-fast
   validation check into a multi-second (or effectively infinite) single
   synchronous call.
4. **Synchronous filesystem calls** (`fs.readFileSync`,
   `fs.writeFileSync`) on large files in the request path instead of
   their Promise/callback equivalents.
5. **A tight synchronous loop** over a large in-memory array or object
   (manual CSV building, deep object cloning, array sort with a custom
   comparator) with no chunking.

## Diagnose
- Reproduce under concurrency: fire one request that hits the suspected
  slow path alongside a burst of trivial requests (e.g. `GET /health`)
  and time the trivial ones. If their latency spikes in lockstep with the
  slow request's duration -- not just the slow request being slow -- that
  confirms event-loop blocking rather than a downstream bottleneck (a
  connection-pool limit produces a different pattern: the fast requests
  queue but the event loop itself keeps responding to new connections).
- Take a CPU profile during the stall: `node --prof` or attach the
  inspector (`node --inspect`) and record a profile while triggering the
  slow request, then look for one long, unbroken synchronous stack frame
  rather than many short ones.
- Grep the suspect handler and everything it calls for the synchronous
  forms specifically: `Sync` suffix (`readFileSync`, `hashSync`), bare
  `JSON.parse`/`JSON.stringify` on anything not provably small, and any
  hand-written loop over request-derived data with no size cap.
- For a suspected regex, test the pattern against a crafted pathological
  input (e.g. repeated ambiguous groups like `(a+)+$` against a long
  non-matching string) in isolation and time it.

## Fix
- Replace synchronous crypto/hashing with the async/Promise variant
  (`crypto.pbkdf2`, `bcrypt.hash`) so the work runs on libuv's thread pool
  instead of the main thread.
- For CPU-bound work with no async library equivalent (custom parsing,
  image processing, heavy computation), move it to a `worker_threads`
  worker or a separate process, and have the route handler `await` a
  message back from the worker -- this actually parallelizes CPU work
  instead of just deferring it.
- For large request/response bodies, use a streaming parser (e.g.
  `stream-json`) instead of buffering the whole body and calling
  `JSON.parse` once, so parsing work is spread across many event-loop
  turns instead of one blocking call.
- Cap input size before doing expensive synchronous work at all (body
  size limits, array length checks) so a pathological single request
  can't monopolize the loop regardless of which code path handles it.
- Replace user-input-facing regexes that can backtrack catastrophically
  with a safer equivalent, or validate with a length cap first.

## Pitfalls
- Moving work into a `worker_threads` pool but creating a new worker per
  request instead of reusing a pool -- worker startup cost then dominates
  for small jobs and you've traded one problem for a new bottleneck.
- "Fixing" this by wrapping the call in `setImmediate` or a resolved
  Promise: that changes *when* the synchronous block runs but not how
  long it blocks once it starts -- it still occupies the loop for its
  full duration, just delayed by one tick.
- Offloading to `worker_threads` without also bounding queue depth --
  if requests arrive faster than workers can process them, the fix moves
  the failure from "frozen event loop" to "unbounded memory growth in a
  worker task queue."

## Verify
Re-run the concurrent load test from the diagnose step after the fix:
the trivial requests' p99 latency should stay flat regardless of whether
the heavy request is in flight, and a CPU profile taken during the heavy
request should show either no single long synchronous frame on the main
thread, or that frame occurring on a worker thread instead of the main
one.
