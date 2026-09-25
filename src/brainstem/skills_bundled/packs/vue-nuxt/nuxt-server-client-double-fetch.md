---
name: nuxt-server-client-double-fetch
description: Fix a Nuxt page that fetches the same data once on the server during SSR and again on the client right after hydration.
triggers: ["nuxt fetches data twice", "duplicate request after hydration", "useFetch runs on server and client", "nuxt payload not used", "double network call ssr"]
permissions: ["READ"]
---

## Symptom
Right after a page loads, the Network tab shows the same data request
happening twice in quick succession: once (invisibly) on the server
during SSR, and then again from the browser immediately after hydration,
even though the data hasn't changed and shouldn't need to be fetched
again.

## Likely causes
1. **Using raw `fetch`/`$fetch` inside `onMounted` or directly in
   `setup()`** instead of `useFetch`/`useAsyncData` -- there's no
   SSR-to-client payload transfer mechanism for a plain fetch call, so
   the client always requests fresh data regardless of what the server
   already did.
2. **`useFetch`/`useAsyncData` given a `key` that isn't identical between
   server render and client hydration** -- e.g. the key incorporates
   `Date.now()`, a random id, or a client-only value -- so the client
   can't find a matching cached payload entry and falls back to
   refetching.
3. **Payload extraction disabled or unavailable** (`experimental.
   payloadExtraction` off, or a caching/CDN layer stripping the embedded
   payload script) so `useNuxtApp().payload.data` doesn't actually
   contain the server's result by the time client-side code runs.
4. **A separate client-only component duplicates a fetch already done by
   a parent's `useAsyncData`**, unrelated to any SSR/payload mechanism --
   just two independent fetch call sites for the same data.

## Diagnose
- Compare Network tab entries right after a fresh full-page load: look
  for two requests to the same endpoint within milliseconds of each
  other.
- View the page source (`view-source:` or `curl`) and search for the
  `__NUXT_DATA__` payload script tag to confirm the server actually
  embedded the fetched result.
- In the browser console immediately after load, run
  `useNuxtApp().payload.data` and check whether the key you expect is
  present -- if it's missing, the client-side call has no cached value to
  reuse and will always refetch.

## Fix
Standardize on `useAsyncData`/`useFetch` (not raw `fetch` in `onMounted`)
so Nuxt automatically serializes the server's result into the payload and
the client-side call resolves from it instead of issuing a new request.
Give the fetch an explicit `key` that's computed identically on server
and client (avoid anything time- or randomness-based in the key itself).
Confirm payload extraction is enabled, especially for statically
generated or heavily cached deployments where an intermediary might strip
embedded payload data.

## Pitfalls
Disabling SSR for the whole page (`ssr: false`) "fixes" the double fetch
by removing the server-side one entirely, but also removes the actual
benefit of SSR (data-complete first paint) -- treat this as a last resort
for pages that truly can't be server-rendered, not a general fix for a
payload/key mismatch.

## Verify
Hard-refresh the page and check the Network tab: the data request should
appear exactly once, embedded in the server response (visible via view
source), with no matching client-side XHR/fetch firing during or right
after hydration.
