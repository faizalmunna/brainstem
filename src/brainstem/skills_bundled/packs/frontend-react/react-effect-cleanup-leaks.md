---
name: react-effect-cleanup-leaks
description: Diagnose memory leaks and "state update on unmounted component" warnings caused by missing useEffect cleanup for subscriptions, timers, or async requests.
triggers: ["memory leak react", "state update on unmounted component", "cant perform a react state update on an unmounted component", "useeffect cleanup", "subscription not cleaned up"]
permissions: ["READ"]
---

## Symptom
A React warning like "Can't perform a React state update on an unmounted
component," a growing memory footprint over time in a long-running SPA
(more listeners/timers active than components currently mounted), or
stale/duplicate side effects (multiple WebSocket connections, multiple
intervals firing) after a component mounts and unmounts repeatedly (e.g.
navigating back and forth between routes).

## Likely causes
1. **A `useEffect` that sets up a subscription, event listener, timer, or
   async request but returns no cleanup function** -- on unmount, the
   subscription/timer keeps running and its callback may still try to
   update state on a component that no longer exists.
2. **An async function inside an effect** (`useEffect(() => { async
   function run() { const data = await fetch(...); setState(data); }
   run(); }, [])`) with no way to cancel or ignore the result if the
   component unmounts before the request resolves.
3. **Event listeners added to `window`/`document`** in an effect without
   removing them in cleanup, accumulating one listener per mount over the
   component's lifetime if it mounts/unmounts repeatedly.
4. **A cleanup function that removes the wrong instance** -- e.g.
   creating a new handler function inline in both the setup and the
   cleanup, so `removeEventListener` doesn't match the exact reference
   passed to `addEventListener`.

## Diagnose
- Find the effect that sets up the resource in question and check whether
  it returns a cleanup function at all.
- For the async-request case, check whether the effect has any mechanism
  (an `ignore`/`cancelled` flag, an `AbortController`) to skip applying
  the result if the component has unmounted by the time it resolves.
- For duplicate-listener bugs, count actual active listeners (browser
  devtools can show registered event listeners on an element) after
  mounting and unmounting the component several times -- the count should
  return to baseline, not keep growing.

## Fix
- Return a cleanup function from every effect that subscribes to
  something external: `return () => subscription.unsubscribe()`,
  `return () => clearInterval(id)`, `return () => window.
  removeEventListener('resize', handler)`.
- For async fetches in effects, use an `AbortController` (aborting it in
  the cleanup function) or a boolean flag set in cleanup that the
  `.then`/`await` continuation checks before calling `setState`, so a
  late-resolving request can't update an unmounted component.
- Ensure the exact same function reference is used for both
  `addEventListener` and `removeEventListener` -- define the handler
  once (e.g. as a named function or via `useCallback` if it needs to be
  referenced elsewhere), not as two separate inline arrow functions.

## Pitfalls
- Wrapping every `setState` call in a `try/catch` or an `isMounted` ref
  check to silence the warning treats the symptom, not the leak -- the
  subscription/timer/listener is still running after unmount; only proper
  cleanup actually stops it.
- Aborting a fetch on cleanup can surface an `AbortError` in a `.catch`
  block that then gets treated as a real error (e.g. shown to the user) --
  explicitly ignore/short-circuit on abort errors rather than letting
  generic error handling catch them.

## Verify
Mount and unmount the component several times in a row (navigate away and
back, or toggle a conditional render) and confirm, via browser devtools or
added logging, that the number of active listeners/timers/subscriptions
returns to zero after each unmount rather than accumulating.
