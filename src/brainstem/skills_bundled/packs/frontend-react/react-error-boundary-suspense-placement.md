---
name: react-error-boundary-suspense-placement
description: Decide where to place Error Boundaries and Suspense boundaries so a failure or slow load in one part of the UI doesn't take down or block unrelated parts.
triggers: ["error boundary placement", "whole page crashes on error", "one component error breaks everything", "suspense boundary", "white screen of death react"]
permissions: ["READ"]
---

## Symptom
Either: an error thrown in one small component (a widget, a single list
item) blanks out the entire page ("white screen of death") because there's
no Error Boundary between it and the app root; or a single slow-loading
piece of data blocks the whole page behind one loading spinner because
there's one `Suspense` boundary at the top instead of several scoped ones.

## Likely causes
1. **No Error Boundary at all**, so any uncaught render error propagates
   to React's default behavior (unmounting the whole tree in production).
2. **Exactly one Error Boundary at the app root**, which does stop total
   white-screens but takes down the entire page for a failure that only
   affected one widget.
3. **Exactly one `Suspense` boundary wrapping the whole page**, so the
   slowest data source anywhere on the page determines when *anything*
   becomes visible, instead of fast sections rendering immediately.
4. **A Suspense boundary placed above data it doesn't actually need to
   wait for**, delaying visible content that had no dependency on the
   slow resource.

## Diagnose
- Trace the component tree from the failing/slow component upward and
  find the nearest Error Boundary / Suspense boundary above it (there may
  be none, or only one far up at the root).
- For "whole page blanks on error," check whether error boundaries exist
  at all, and if so, at what level of granularity.
- For "whole page waits for the slowest thing," check whether independent
  sections of the page share one Suspense boundary that could instead be
  split so each section streams in independently.

## Fix
- Place Error Boundaries around independently-failable, independently-
  useful sections (a sidebar, a comments widget, a single card in a grid)
  so one failure degrades gracefully (a fallback UI for that section)
  rather than taking down the page. Keep one boundary at the root too, as
  a last-resort catch-all, but don't rely on it as the only one.
- Give each Error Boundary a fallback appropriate to its scope -- a small
  inline "couldn't load this" for a widget, not a full-page error screen,
  unless the failure genuinely is page-fatal.
- Split one large `Suspense` boundary into several scoped around each
  independently-loadable section, so fast sections render immediately and
  slow sections show their own loading state without blocking the rest.
- Pair each Suspense boundary with an Error Boundary above or around it --
  a component that suspends can also throw, and without an Error Boundary
  nearby, that failure propagates further up than intended.

## Pitfalls
- Over-splitting into a boundary per tiny component adds visual "popping
  in" of many separate loading states, which can feel worse than a single
  well-designed skeleton for a section that's expected to load together.
- An Error Boundary catches errors during rendering, lifecycle methods,
  and constructors of the tree below it, but *not* errors in event
  handlers, async code outside of render (a rejected promise inside a
  `useEffect` not surfaced back into render), or in the boundary
  component itself -- those need their own explicit handling (try/catch
  in the handler, or converting the async error into thrown render-time
  state).

## Verify
Force an error in one scoped section (a temporary `throw` in dev) and
confirm only that section's fallback UI appears while the rest of the
page keeps working; separately, throttle one data source and confirm only
its own Suspense boundary shows a loading state while independent
sections render immediately.
