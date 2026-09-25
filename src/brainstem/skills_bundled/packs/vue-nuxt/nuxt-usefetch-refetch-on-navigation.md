---
name: nuxt-usefetch-refetch-on-navigation
description: Stop useFetch or useAsyncData from firing a fresh network request every time a user revisits a page with unchanged params.
triggers: ["useFetch refetching every navigation", "useAsyncData runs again on route change", "duplicate request on revisit nuxt", "useFetch cache not working", "nuxt refetches same data"]
permissions: ["READ"]
---

## Symptom
Navigating away from a page and back to it (client-side, no full reload)
causes `useFetch`/`useAsyncData` to fire a brand-new network request every
time, visible in the Network tab, even though the URL and params are
identical to the previous visit.

## Likely causes
1. **No explicit `key` passed**, so Nuxt derives one automatically; if the
   composable is called in a context where that derivation isn't stable
   across remounts (e.g. inside a component that gets destroyed and
   recreated), the implicit key doesn't match a previous cached entry.
2. **Payload caching only covers the SSR-to-client handoff on first load**
   -- by default there's no persistent cache across subsequent client-side
   navigations, so revisiting a page later in the same SPA session is
   expected to refetch unless you explicitly wire up `getCachedData`.
3. **A new params object literal is created on every render** (e.g. `{
   category: props.category }` inline) and passed as a reactive source;
   `watch` (on by default) sees a new object reference each time and
   treats it as a change even when the actual values are unchanged.
4. **The page component itself is destroyed and recreated on navigation**
   (e.g. keyed by `route.fullPath` on `<NuxtPage>`), so this isn't a
   caching bug at all -- it's a fresh mount correctly fetching fresh data,
   and the real question is whether that remount is intentional.

## Diagnose
- Open the Network tab, navigate away and back several times, and note
  whether a new request fires every time or only when params actually
  differ.
- In the browser console, inspect `useNuxtApp().payload.data` (or
  `static.data`) right after navigating back to see whether a matching
  key's data is already present -- if it is but a request still fired,
  the key/`getCachedData` wiring is the issue, not the absence of cached
  data.
- Add an `onMounted`/`onUnmounted` log in the page component to check
  whether it's actually being destroyed and recreated on each navigation.

## Fix
Pass an explicit, stable `key` to `useFetch`/`useAsyncData` so Nuxt can
recognize repeated calls as "the same request," and implement
`getCachedData` to read from the existing payload/cache before deciding
to refetch, rather than relying on the default derived key. For the
object-identity issue, wrap the params in a `computed` (or otherwise keep
a stable reference) so `watch` only sees a change when a real field
changes, not on every render. If the remount is intentional (e.g. reset
scroll/local state per navigation), accept the refetch as correct
behavior rather than fighting it.

## Pitfalls
Reaching for `{ immediate: false }` or disabling `watch` entirely to make
the refetching stop can silently break legitimate reactivity -- the page
then never updates when a route param genuinely changes. Fix the key/
cache strategy first; only disable automatic behavior once you've
confirmed the remaining refetch is truly redundant, not a real
dependency.

## Verify
Navigate away and back to the page multiple times while watching the
Network tab: confirm the request fires once for a given set of params and
does not re-fire on revisit unless a param actually changed, while a
genuine param change still triggers exactly one new request.
