---
name: react-context-rerender-storm
description: Diagnose every consumer of a React Context re-rendering whenever any field in the context value changes, even fields they don't read.
triggers: ["context causes rerenders", "every consumer rerenders", "context performance", "usecontext rerenders everything", "context value changes too often"]
permissions: ["READ"]
---

## Symptom
A large number of components consuming the same Context all re-render
whenever *any* field of the context value changes, even components that
only read one unrelated field -- visible as a wide, flat block of
re-renders in the Profiler every time one small piece of shared state
updates.

## Likely causes
1. **A single context holding many unrelated fields** (e.g. `{ user,
   theme, notifications, sidebarOpen }`) -- `useContext` re-renders on
   *any* change to the value object, not just the fields a given consumer
   actually destructures.
2. **The provider recreating the context value object every render**
   (`<Ctx.Provider value={{ user, setUser }}>` without memoization), so
   every consumer re-renders on every provider render regardless of
   whether the meaningful data changed.
3. **Frequently-changing state (e.g. mouse position, a live counter)
   sharing a context with rarely-changing state (e.g. current user)**,
   so the rare-change consumers pay the cost of the frequent-change
   consumers' updates.

## Diagnose
- Identify the context in question and list every field on its value
  object, then check which components actually destructure which fields.
- Check whether the provider wraps its value object in `useMemo` keyed on
  its actual dependencies, or creates a fresh object literal every
  render.
- In the Profiler, confirm the pattern: many sibling/cousin components
  re-rendering simultaneously whenever one specific, frequently-changing
  piece of state updates.

## Fix
- Split one large context into several smaller contexts by
  change-frequency and concern (e.g. `UserContext`, `ThemeContext`,
  `SidebarContext` instead of one `AppContext`) so a consumer only
  re-renders when the specific context it reads changes.
- Wrap the provider's value in `useMemo` with an accurate dependency
  array so a provider re-render (for unrelated reasons) doesn't produce
  a new value reference and cascade to every consumer.
- For frequently-changing values that many components need to *read* but
  rarely need to *react to on every change*, consider a ref-based or
  external-store pattern (e.g. `useSyncExternalStore`) instead of
  Context, so reads don't imply automatic re-render subscriptions.
- If only specific fields are hot, split state and actions into separate
  contexts (a rarely-changing "state" context and a stable "dispatch"
  context) so components that only need to trigger updates don't
  re-render when the state itself changes.

## Pitfalls
- Splitting into many small contexts without a real usage-pattern
  analysis just moves the same object shape around and can make the
  provider tree deeply nested for no measured benefit -- profile first to
  confirm context re-renders are actually the bottleneck, not general
  over-rendering (see `react-unnecessary-rerenders`).
- Memoizing the context value but still creating new function references
  for actions inside it every render defeats the memoization for any
  consumer that only cares about the actions -- memoize functions with
  `useCallback` too, or keep stable action references outside the render
  entirely (e.g. via a reducer's dispatch, which is stable by design).

## Verify
Record a Profiler session before and after the split/memoization: a
change to one context's value should now only re-render its own
consumers, and components with no dependency on the changed context
should no longer appear in that render's list.
