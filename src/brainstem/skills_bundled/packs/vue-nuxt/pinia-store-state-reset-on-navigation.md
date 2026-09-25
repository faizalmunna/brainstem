---
name: pinia-store-state-reset-on-navigation
description: Diagnose a Pinia store whose state unexpectedly resets to its initial values when the user navigates to another route and back.
triggers: ["pinia store resets on navigation", "pinia state cleared route change", "store data disappears after navigating", "pinia not persisting between pages", "pinia state lost"]
permissions: ["READ"]
---

## Symptom
Data set into a Pinia store on one page (e.g. a multi-step form's
progress, a loaded list) is gone -- back to its initial default -- when
the user navigates to another route and returns, even though Pinia stores
are supposed to be shared, app-wide singletons.

## Likely causes
1. **Populate-once logic living in a page's `onMounted`** that
   unconditionally sets/resets store state every time that page mounts,
   which looks like "the store reset" but is actually the page
   re-initializing it on every visit.
2. **A global route middleware or plugin that runs on every navigation**
   and calls `store.$reset()` or reassigns store state unconditionally,
   rather than only on the specific transition (e.g. logout) that should
   clear it.
3. **The page component is destroyed and recreated on navigation** (e.g.
   `<NuxtPage :key="route.fullPath">`), and the store-populating code is
   incorrectly assumed to be tied to component lifecycle instead of being
   independent of it.
4. **Pinia not wired up correctly for SSR** (missing/misconfigured
   `@pinia/nuxt` module registration), so a fresh Pinia instance -- and
   thus fresh store state -- gets created on certain navigations instead
   of reusing the single app-wide instance.

## Diagnose
- Add a one-time `console.log('store created')` inside the store
  definition itself (not an action) -- if this logs again after
  navigating back, a new store instance is being created, which points to
  cause 3 or 4, not a data-clearing action.
- Grep global middleware (`middleware/*.global.ts`) and app plugins for
  `.$reset()` or direct state assignment that runs unconditionally on
  every route change.
- Use Vue/Pinia devtools to inspect the store's state timeline across the
  navigation and see exactly which action or mutation fired right before
  the value reverted.

## Fix
Move logic that should run once (populate on first load) out of a page's
`onMounted` and into the store's own action, guarded so it's a no-op if
data already exists (`if (this.items.length) return`). Scope any
`$reset()`/state-clearing calls to the specific event that should cause
them (logout, explicit "start over" action) rather than a global
middleware that fires on every navigation. Confirm `@pinia/nuxt` is
registered as a module (not manually re-created per request) so the SSR
and client share one store instance per app lifecycle as intended.

## Pitfalls
Reaching for a persistence plugin (`pinia-plugin-persistedstate`,
localStorage-backed state) to paper over the symptom fixes the visible
data loss but doesn't address a real double-instantiation or unconditional
reset bug -- and it introduces new problems like stale data surviving
across browser tabs or logins.

## Verify
Set a distinctive value in the store, navigate to another route, navigate
back, and confirm via Pinia devtools (or a log of the store's identity/id
set once at creation) that the same store instance is still alive and the
value you set is still present, rather than reverted to its default.
