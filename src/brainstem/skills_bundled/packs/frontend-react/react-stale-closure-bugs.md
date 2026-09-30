---
name: react-stale-closure-bugs
description: Diagnose bugs where an event handler, effect, or timer callback uses an old value of state/props from when it was created.
triggers: ["stale closure", "old value in callback", "state is stale", "using outdated state", "useeffect sees old value", "setinterval sees old state"]
permissions: ["READ"]
---

## Symptom
A callback (event handler, `setTimeout`/`setInterval` callback, effect
cleanup, or a function passed to a subscription) reads a value that's
"stuck" at whatever it was when the function was created, ignoring later
updates -- classic tell: a counter that always logs 0, or a handler that
uses the first-ever prop value forever.

## Likely causes
1. **`useEffect`/`useCallback` with an incomplete dependency array** --
   the callback closes over a variable from the render it was created in,
   but the effect only re-runs (and recreates the callback) on some other
   trigger, so it never sees updates.
2. **`setInterval`/`setTimeout` set up once in a `useEffect` with `[]`**
   deps, whose callback body reads state -- the interval keeps calling the
   original closure forever, never the current one.
3. **A subscription/event listener registered once** (e.g. WebSocket
   `onmessage`, DOM event listener) whose handler closes over stale state
   because the listener itself is never re-registered when state changes.
4. **Passing a memoized callback down several levels** where an
   intermediate component doesn't propagate updates, so a grandchild
   holds onto the first version indefinitely.

## Diagnose
- Find the `useEffect`/`useCallback`/`useMemo` whose dependency array is
  missing a variable the callback body actually reads -- an ESLint
  `react-hooks/exhaustive-deps` warning is often already pointing at it;
  don't silence that lint rule without understanding why first.
- For interval/timeout bugs specifically, check whether the interval is
  set up in an effect with `[]` deps while its body references state or
  props.
- Add a temporary `console.log` inside the callback logging the value in
  question and compare it against the value logged at the top of the
  component's render -- if the callback's value never advances past the
  first render's, it's a stale closure.

## Fix
- Add the missing dependency to the effect/callback's dependency array so
  it gets recreated (and, for effects, cleaned up and re-run) when that
  value changes.
- For intervals/timeouts that need the *latest* value without
  re-creating the timer itself, use a ref updated every render
  (`useEffect(() => { ref.current = value })`) and read `ref.current`
  inside the timer callback instead of closing over the state variable.
- For the functional-update case (state derived from previous state),
  use the updater-function form (`setCount(c => c + 1)`) instead of
  reading the closed-over `count` directly -- this sidesteps the
  staleness for that specific pattern entirely.

## Pitfalls
- Adding every reported missing dependency mechanically can cause an
  effect to re-run (and a subscription to re-register) far more often
  than intended -- if that's the actual problem, the ref-based pattern
  above is usually the right fix, not more dependencies.
- Silencing `exhaustive-deps` with an inline disable comment "to make the
  warning go away" is how most stale-closure bugs get shipped in the
  first place; treat every instance as a decision, not a formality.

## Verify
Reproduce the original symptom (counter incrementing correctly, handler
using the latest prop, etc.) with a value that changes multiple times
after the callback is first created, and confirm the callback observes
each new value, not just the first.
