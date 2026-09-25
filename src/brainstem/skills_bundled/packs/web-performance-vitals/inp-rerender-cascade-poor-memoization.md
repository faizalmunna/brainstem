---
name: inp-rerender-cascade-poor-memoization
description: Fix a poor INP score traced to one interaction re-rendering a large tree of components instead of one large blocking function.
triggers: ["INP high but no single slow function", "typing causes many small renders", "interaction slow due to many components updating", "INP processing time spread across renders"]
permissions: ["READ"]
---

## Symptom
INP is flagged poor for an interaction, but unlike a single heavy
synchronous handler, the Performance trace's Processing phase shows *many*
small render/update calls spread across dozens or hundreds of components
rather than one obvious long function -- typing a character or toggling a
filter visibly lags even though no individual piece of work looks
expensive in isolation; this is an architectural fan-out problem, not a
single slow computation.

## Likely causes
1. **State that changes on every keystroke/interaction lives at a high
   level of the component tree** with no memoization boundaries below it,
   so the update cascades and re-renders a large subtree that doesn't
   actually depend on the changed value.
2. **Components consuming a shared context/store re-render on any change
   to that store**, not just the slice they read, multiplying the number
   of components that redo work for a single state change.
3. **List items each re-render individually because their props include a
   new reference on every parent render** (inline callbacks/objects), so
   `memo` on the list item does nothing and every row repaints on every
   keystroke even if only one row's data is relevant.
4. **A derived/computed value is recalculated inside render on every
   update** for many components simultaneously, rather than once and
   memoized, multiplying a cheap-looking calculation by the number of
   components doing it.

## Diagnose
- In DevTools > Performance, expand the Processing phase of the flagged
  interaction and confirm the pattern -- many similarly-shaped, short
  call-stack entries repeated across the timeline, rather than one wide
  block -- which distinguishes this from a single heavy handler.
- Use the React DevTools Profiler on the same interaction and check the
  "ranked" view for the number of components that rendered, not just
  their individual durations -- a high *count* of rendered components for
  a small state change is the signal, even if each is individually cheap.
- Check whether the components that rendered actually depended on the
  changed state, using the Profiler's "why did this render" info, to
  confirm they're rendering unnecessarily rather than legitimately.
- Correlate the total count of rendered components against the total
  Processing time in the Performance trace -- roughly linear scaling with
  component count confirms fan-out is the bottleneck, not one slow piece.

## Fix
Contain the blast radius of the state change so it only touches the
components that actually depend on it, rather than trying to make each
individual re-render faster (which won't help if the count is the
problem). Concretely: colocate frequently-changing state close to where
it's consumed instead of at a shared ancestor, so updates don't have to
propagate through and re-render unrelated siblings; split large
contexts/stores by concern (or use a selector-based state library that
only re-renders subscribers whose selected slice changed) so a change to
one field doesn't re-render every consumer of the store; memoize list item
components together with stable callback/prop references (`useCallback`
with correct dependencies, or moving the callback reference out of the
per-render closure) so `memo` can actually skip unaffected rows; and hoist
per-render derived calculations to a memoized selector computed once
rather than recomputed inside every affected component.

## Pitfalls
- Adding `React.memo` to every component in the tree without also fixing
  the underlying unstable prop references (cause 3) does nothing --
  verify the actual prop identity is stable before concluding
  memoization "isn't working."
- Splitting context/state too finely can fragment related data that
  genuinely needs to update together, forcing awkward cross-context
  coordination -- split along real independence boundaries, not
  arbitrarily.
- This looks similar to a plain "unnecessary re-renders" skill, but the
  fix here targets fan-out across many components triggered by one
  interaction (an INP/interaction-responsiveness lens); if only one
  component renders too often for unrelated reasons with no interaction
  latency implication, that's the narrower re-render problem, not this
  one.

## Verify
Re-run the React DevTools Profiler on the same interaction and confirm
the number of rendered components dropped to only those that actually
depend on the changed state, then re-check the Performance trace's
Processing phase duration and the real-user INP value for that
interaction to confirm both improved together.
