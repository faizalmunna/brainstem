---
name: react-state-management-choice
description: Decide where a given piece of state should live -- local useState, lifted/Context, a client-state library, or server-state (data-fetching) caching -- instead of defaulting to one tool for everything.
triggers: ["should i use redux", "where should this state live", "context vs redux", "do i need a state library", "react query vs context", "server state vs client state"]
permissions: ["READ"]
---

## Symptom
A codebase either (a) reaches for a global state library/Context for
state that's genuinely local to one component, causing unnecessary
complexity and re-render surface area, or (b) has server-fetched data
manually copied into local/global client state with hand-rolled loading/
error/cache-invalidation logic that a data-fetching library would give for
free, or (c) has ad-hoc prop-drilling for state that's actually shared
widely enough to justify lifting it.

## Likely causes
This is a decision skill, not a bug-diagnosis skill -- the "cause" is
usually that the choice was made by habit/familiarity rather than by
asking what kind of state this actually is.

## Diagnose
Classify the state before picking a tool:
1. **Server state** (anything that originates from an API/database and
   can go stale) -- has fetching, caching, revalidation, and loading/error
   states as first-class concerns, not just "a value."
2. **Local UI state** (a toggle, an input's current value, whether a
   dropdown is open) -- lives and dies with one component, nothing else
   needs to know about it.
3. **Shared client state** (theme, current user session info already
   fetched, a multi-step form's in-progress values) -- multiple, possibly
   distant components need to read or write it, but it doesn't come from
   a live server resource.
4. **URL state** (current filters, selected tab, pagination page) -- state
   that should survive a refresh and be shareable via link, which neither
   local state nor a client store gives you for free.

## Fix
- **Server state** -> use a dedicated data-fetching/caching library (React
  Query/TanStack Query, SWR, or the framework's built-in equivalent like
  Next.js's fetch caching) rather than copying fetched data into
  `useState`/Context and hand-rolling refetch/staleness logic.
- **Local UI state** -> plain `useState`/`useReducer` in the component
  that owns it. Don't lift it or put it in Context just because it feels
  more "proper" -- colocation is the correct default.
- **Shared client state** -> lift to the nearest common ancestor and pass
  down, or use Context (split by concern, see
  `react-context-rerender-storm`) for state read widely across the tree;
  reach for a dedicated client-state library (Zustand, Jotai, Redux)
  specifically when the shared-state graph gets complex enough that prop-
  drilling or a single context becomes unwieldy -- not by default.
- **URL state** -> store it in the URL (query params/route segments) via
  the router, so it's shareable and survives refresh, and derive
  component state from it rather than maintaining a parallel copy.

## Pitfalls
- Introducing a global state library for what turns out to be local UI
  state adds indirection (actions, selectors, boilerplate) with no
  benefit and makes the component harder to reason about in isolation.
- Using `useState` + `useEffect` to fetch and store server data manually
  is the single most common source of stale-data, race-condition (fetch
  A resolves after fetch B despite starting first), and duplicate-request
  bugs in React codebases -- if a data-fetching library is available,
  hand-rolled fetching in `useEffect` should be the exception, not the
  default.
- Mirroring URL state into `useState` ("sync" the two with an effect)
  instead of treating the URL as the single source of truth creates a
  class of bugs where the two get out of sync on back/forward navigation.

## Verify
For a given piece of state, ask: "if this component unmounted and
remounted, should the value survive?" and "does anything else need to
react to this changing?" -- the answers place it in exactly one of the
four categories above; if the current implementation doesn't match, that's
the concrete thing to change.
