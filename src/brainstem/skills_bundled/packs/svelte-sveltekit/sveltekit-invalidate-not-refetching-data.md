---
name: sveltekit-invalidate-not-refetching-data
description: Diagnose SvelteKit invalidate or invalidateAll calls that complete without triggering the expected load function to rerun and refetch data.
triggers: ["invalidate not working sveltekit", "invalidateAll not refetching", "depends not triggering reload", "sveltekit stale data after mutation", "load not rerunning after invalidate"]
permissions: ["READ"]
---

## Symptom
Code calls `invalidate('app:something')` or `invalidateAll()` after a
mutation (a form submit, a manual `fetch` to an API route), the call
resolves without error, but the page keeps showing the old data -- the
associated `load` function never reruns, or reruns but returns the same
stale result.

## Likely causes
1. **The dependency key used to invalidate doesn't match what the load
   function declared.** `depends('app:todos')` inside the load function
   and `invalidate('app:todo')` (typo, or a mismatched string) at the call
   site are two different keys as far as SvelteKit is concerned -- no
   error is raised, it just silently matches nothing.
2. **The load function uses the global `fetch` instead of the `fetch`
   passed into its arguments.** SvelteKit only tracks same-origin URL
   dependencies for requests made through the load function's own
   `fetch` parameter -- a request made with the ambient global `fetch`
   (or an already-bound `fetch` imported from elsewhere) is invisible to
   `invalidate(url)`, so invalidating that URL has nothing to invalidate.
3. **A URL-based `invalidate(url)` call doesn't match how the load
   function actually requested it** -- e.g. the load fetched
   `/api/todos?page=1` but the invalidation call passes
   `/api/todos` without the query string, or an absolute vs. relative URL
   mismatch -- SvelteKit compares URLs, and a partial or differently-
   formed URL won't match.
4. **An application-level cache sits in front of the load function**
   (e.g. a module-scoped `Map` memoizing fetch results, or a data layer
   with its own TTL) -- SvelteKit correctly reruns the load function, but
   the load function itself returns a cached value instead of doing fresh
   work.
5. **`invalidate()`/`invalidateAll()` is called without `await`ing it**
   in a context where the caller then immediately reads page data
   expecting it to already be fresh (e.g. right before a `goto()`) --
   the refetch is in flight but hasn't resolved yet when it's inspected.

## Diagnose
- Grep for every `depends(` call and every `invalidate(`/`invalidateAll(`
  call site; line up the exact key strings used on both sides -- a single
  character mismatch is the most common root cause.
- Check the load function's fetch calls: is it destructuring `fetch` from
  the load event (`export async function load({ fetch }) { ... }`) and
  using that, or calling a module-level `fetch`/an axios instance that
  ignores it?
- Log the exact URL string passed to `invalidate()` and compare it
  byte-for-byte against the URL the load function's `fetch` call actually
  requested (check the Network tab's request URL).
- Temporarily bypass any custom caching layer (comment it out or force a
  cache miss) to isolate whether SvelteKit is rerunning the load function
  at all -- add a `console.log` at the top of load to confirm.

## Fix
- Use one canonical dependency string per logical resource and reference
  it via a shared constant (not a hand-typed literal in multiple places)
  so `depends()` and `invalidate()` can never drift apart.
- Always destructure and use the `fetch` provided in the load event's
  arguments for any request whose freshness should be controlled by
  SvelteKit's invalidation system -- reserve the global `fetch` for
  requests that intentionally shouldn't participate in that tracking.
- When invalidating by URL, either match the exact URL the load function
  used (including query string) or invalidate by custom key via
  `depends()` instead of relying on URL matching, which is more precise
  and immune to formatting differences.
- If an app-level cache is needed, key its invalidation off the same
  event that triggers `invalidate()`/`invalidateAll()` so both layers
  clear together, or remove the extra caching layer if SvelteKit's own
  load-function reruns are sufficient.
- `await` `invalidate()`/`invalidateAll()` wherever subsequent code
  depends on the refreshed data being in place.

## Pitfalls
- Switching everything to `invalidateAll()` to sidestep key-matching bugs
  causes the over-refetching problem covered separately -- fix the key
  mismatch instead of widening the blast radius.
- Adding a custom cache-busting query parameter to every fetch call as a
  workaround for a dependency-tracking bug masks the real issue and adds
  permanent, unnecessary cache-defeating overhead to production traffic.

## Verify
Trigger the mutation, call the specific `invalidate(key)` (or
`invalidateAll()`), and confirm via a load-function log (or Network tab)
that a genuinely new request fires and the UI updates with the new value
-- then confirm an unrelated key/URL does *not* trigger a refetch, proving
the invalidation is scoped correctly rather than accidentally working via
a blanket `invalidateAll()`.
