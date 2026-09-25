---
name: sveltekit-load-function-rerunning-unexpectedly
description: Diagnose a SvelteKit load function that refetches data on client-side navigations where nothing it actually depends on has changed.
triggers: ["load function rerunning", "sveltekit refetching on every navigation", "load runs too often", "page data refetches unnecessarily", "sveltekit load dependency tracking"]
permissions: ["READ"]
---

## Symptom
Navigating between routes (via `<a href>` or `goto`) causes a `load`
function to run again -- and its network request to refire -- even though
the page it's attached to looks like it shouldn't care about whatever
changed in the URL, or about an unrelated invalidation elsewhere in the
app.

## Likely causes
1. **The load function reads the whole `url` object** (or
   `url.searchParams` broadly) instead of the specific param it needs.
   SvelteKit tracks *which parts* of `url` a load function accessed during
   its last run and reruns it if any of those tracked parts change --
   reading `url.searchParams` as a whole (e.g. iterating it, or passing it
   into a function) makes SvelteKit treat almost any query-string change
   as relevant, even for unrelated params.
2. **A broad `invalidateAll()` call** somewhere in the app (often added
   after a form submission "just to be safe") reruns *every* load function
   on the page, including ones with no real dependency on what changed.
3. **The page's load calls `await parent()`**, and an ancestor
   `+layout.js`/`+layout.server.js` reruns for its own reasons (e.g. it
   calls `depends('app:session')` and something invalidates that key) --
   the child load then reruns too, because `parent()` is itself a tracked
   dependency.
4. **The load function uses the provided `fetch` against a same-origin
   endpoint**, and something elsewhere calls `invalidate(url)` with a URL
   that matches more broadly than intended (e.g. invalidating a whole API
   prefix instead of one exact resource).

## Diagnose
- Add a `console.log('load ran', url.pathname, url.search)` at the top of
  the load function and reproduce the navigation; compare what actually
  changed in the logged URL against what the component visually needs.
- Search the load function body for any bare reference to `url` (not
  `url.pathname` or one named `url.searchParams.get('x')`) -- broad reads
  are the most common cause of over-tracking.
- Grep the codebase for `invalidateAll(` and check every call site's
  context -- especially ones inside `use:enhance` callbacks or global
  error handlers that fire more often than intended.
- Check whether the page's `+page.js`/`+page.server.js` calls `await
  parent()` and, if so, temporarily log inside the parent layout's load
  to see if *it's* the one rerunning and dragging the child along.

## Fix
- Narrow what the load function reads from `url` to exactly the fields it
  needs (`url.searchParams.get('page')` rather than passing around
  `url.searchParams` itself) -- SvelteKit's dependency tracking is
  fine-grained on the properties actually accessed, so precision here
  directly reduces reruns.
- Replace blanket `invalidateAll()` calls with a targeted `invalidate(key)`
  using a custom dependency string set via `depends('app:whatever')` in
  the specific load function that needs to refresh -- this scopes the
  invalidation to exactly the loads that declared interest in that key.
- If a child load only needs `parent()` for typing/data merging but
  doesn't actually need to react to every parent recomputation, consider
  restructuring so the shared value comes from a narrower source (e.g. a
  dedicated small layout load, or `locals`, rather than a layout that also
  recomputes unrelated things).
- When invalidating by URL, match it exactly (or use a function predicate
  passed to `invalidate()`) instead of a prefix that unintentionally
  matches multiple endpoints.

## Pitfalls
- Removing all `invalidateAll()` calls in favor of manual `invalidate()`
  everywhere can under-invalidate and leave stale data displayed after a
  mutation -- scope it down deliberately per case, don't blanket-replace.
- Destructuring `url.searchParams` into a plain object at the top of load
  "to avoid the whole-object read" doesn't actually help -- the read
  still happened during that destructure, and depending on how it's done
  can track even more broadly than a targeted `.get()` call.

## Verify
Reproduce the exact navigation that used to trigger the unwanted refetch,
watch the load-function log/network request, and confirm it no longer
fires for URL or invalidation changes unrelated to the fields the load
function actually reads, while still firing correctly when those specific
fields do change.
