---
name: react-unnecessary-rerenders
description: Diagnose and fix a component (or whole subtree) re-rendering far more often than the data it displays actually changes.
triggers: ["component re-renders too much", "why does this rerender", "typing lags", "input feels slow", "rerender storm", "excessive rerenders"]
permissions: ["READ"]
---

## Symptom
A component re-renders on every keystroke/scroll/tick even though its own
props/state didn't meaningfully change, visible as input lag, dropped
frames, or a suspiciously hot component in the React DevTools Profiler.

## Likely causes
1. **A new object/array/function literal created every render** passed as
   a prop (`onClick={() => ...}`, `style={{...}}`, `data={[...]}`) --
   `React.memo` can't help because the prop is a new reference every time
   even if its contents are identical.
2. **Context value object recreated every render** of the provider, so
   every consumer re-renders even if the specific field they read didn't
   change (see the separate `react-context-rerender-storm` skill for the
   deep version of this).
3. **State lifted higher than it needs to be**, so a state update
   re-renders a large parent subtree instead of just the component that
   actually needs the new value.
4. **A parent re-rendering for unrelated reasons** with no memoization
   anywhere in between, so every child re-renders even though `memo`
   would have stopped most of them.
5. **Derived values recomputed and passed down as new references** without
   `useMemo`, even when the underlying data hasn't changed.

## Diagnose
- Use React DevTools Profiler: record an interaction, then look at which
  components re-rendered and why (the Profiler shows "why did this
  render" hints -- props changed, state changed, parent rendered).
- For a specific suspect component, temporarily wrap it in
  `React.memo` with a custom comparator that `console.log`s which prop
  changed -- this pinpoints reference-vs-value mismatches fast.
- Check whether the component's parent re-renders on every keystroke of
  an unrelated input; if so, the state driving that input is scoped too
  broadly (cause 3).

## Fix
- Wrap event handlers passed as props in `useCallback` with the correct
  dependency array, and object/array literals passed as props in
  `useMemo`, when the receiving component is wrapped in `React.memo`.
- Push state down to the smallest component that needs it (colocate
  state), so unrelated siblings don't re-render when it changes.
- Split a large context into multiple smaller contexts by concern, so a
  component only re-renders when the specific slice it reads changes.
- For expensive derived computations, use `useMemo` keyed on the actual
  inputs, not on a recreated object that wraps them.

## Pitfalls
- Wrapping everything in `useMemo`/`useCallback`/`React.memo`
  "defensively" adds real overhead (comparison cost, memory) and makes
  code harder to read; apply it where profiling shows an actual hot path,
  not everywhere.
- `React.memo` with a shallow comparator does nothing if you're still
  passing new object/array/function literals as props -- the memoization
  and the literal-avoidance have to be fixed together, not one without
  the other.
- Over-splitting state into many individual `useState` calls to avoid
  re-renders can fragment logic that belongs together; prefer colocating
  related state in one object/reducer if the fields always change
  together anyway.

## Verify
Re-run the Profiler recording after the fix and confirm the specific
component no longer appears in the render list for the interaction that
shouldn't affect it (e.g. typing in input A no longer re-renders unrelated
component B).
