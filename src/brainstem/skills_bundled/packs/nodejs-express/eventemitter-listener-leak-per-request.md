---
name: eventemitter-listener-leak-per-request
description: Diagnose steadily growing memory and MaxListenersExceededWarning caused by an Express handler attaching an EventEmitter listener on every request without removing it.
triggers: ["MaxListenersExceededWarning", "memory grows with request volume", "possible EventEmitter memory leak", "listener count keeps increasing", "node heap grows over time under load"]
permissions: ["READ"]
---

## Symptom
The Express process's memory usage climbs steadily and roughly
proportionally to request volume rather than stabilizing under steady
load, eventually leading to a restart from an OOM kill or degraded GC
pause times. Often accompanied by Node printing
`(node) warning: possible EventEmitter memory leak detected. 11
listeners added` (or similar) pointing at a specific emitter, though the
warning can be absent if the leak is spread across many different
emitter instances rather than one.

## Likely causes
1. **A request handler subscribes to a long-lived, shared EventEmitter**
   (a singleton event bus, a shared DB client's `error`/`notification`
   event, a shared WebSocket/pubsub client) on every request with `.on()`
   and never calls `.off()`/`.removeListener()` -- each request adds one
   more listener that outlives the request and is never cleaned up.
2. **A listener closure captures per-request objects** (the `req`/`res`
   objects, a large payload, a DB connection) -- even if the listener
   count itself is bounded, each leaked listener keeps its entire closure
   scope alive, so the effective leak size per listener can be large.
3. **Response/error listeners attached to `req`/`res` or to a stream
   created per-request, with the intent to remove them, but the removal
   code lives on a code path that doesn't always run** (e.g. cleanup only
   happens on the success path, not on an early return or a thrown
   error), so listeners accumulate specifically on the request's error or
   early-exit paths.
4. **Using `once()`-appropriate events with `on()` instead**, so a
   listener meant to fire exactly one time per request keeps firing (and
   getting re-added on the next request) instead of self-removing.

## Diagnose
- Watch for `MaxListenersExceededWarning` in logs, and if present, note
  which emitter and event name it names -- that's usually enough to
  locate the `.on()` call directly with a grep for that event name.
- Take two heap snapshots under sustained load (e.g. via
  `node --inspect` and Chrome DevTools' Memory tab, or
  `v8.getHeapSnapshot()`), separated by a period of steady request
  traffic with no expected state growth, and diff them -- if `Closure` or
  the specific emitter's internal `_events` structure shows growth
  proportional to requests served in that window, that confirms a
  per-request listener leak rather than a one-time startup allocation.
- Grep every long-lived emitter (module-level singletons, a shared client
  exported from a `db.js`/`bus.js` module) for `.on(`/`.addListener(`
  calls that appear inside a route handler function body, as opposed to
  module-level setup code that runs once at startup -- the latter is
  normal, the former is the leak pattern.
- For a specific suspected emitter, log `emitter.listenerCount(eventName)`
  periodically (or on each request) and confirm it grows unboundedly
  instead of staying constant.

## Fix
- Remove the listener explicitly when the request completes: capture a
  reference to the handler function (not an inline arrow function that
  can't be referenced later) and call
  `emitter.off(eventName, handlerRef)` in a `finally` block, or in both
  the success path and an error-handling path, so it runs regardless of
  how the request ends.
- Prefer `emitter.once(eventName, handler)` when the listener is only
  ever meant to handle a single occurrence -- it self-removes after
  firing, eliminating the accumulation risk structurally instead of
  relying on remembering to call `off()`.
- Where the pattern is "wait for one event relevant to this request,"
  attach the listener on request start and guarantee removal by wiring
  cleanup to `res.on('close', cleanup)` (fires on the response actually
  ending, including client disconnects) rather than only to the
  success-path code.
- If many requests genuinely need to react to the same shared event,
  invert the pattern: have a single, permanent listener on the shared
  emitter that dispatches to a request-scoped registry (a Map keyed by
  request id) instead of attaching a new raw listener per request.

## Pitfalls
- Calling `emitter.setMaxListeners(0)` (unlimited) to silence the warning
  "fixes" the visible symptom while leaving the actual leak in place --
  it just delays the OOM crash and removes the early warning signal.
- Passing a fresh arrow function to `off()` that isn't reference-equal to
  the one passed to `on()` silently does nothing -- `removeListener`
  matches by function reference, so the handler must be stored in a
  variable and reused for both calls.
- Cleaning up only on `res.on('finish', ...)` misses client-disconnect
  cases where the response never finishes normally -- use `res.on('close',
  ...)`, which fires in both the normal-completion and disconnect cases.

## Verify
Run a sustained load test (e.g. a few thousand requests to the affected
route) and plot `process.memoryUsage().heapUsed` and, if applicable,
`emitter.listenerCount(eventName)` over the run -- both should plateau
rather than grow linearly with request count after the fix, and the
`MaxListenersExceededWarning` (if it was present before) should no
longer appear.
