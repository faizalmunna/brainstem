---
name: angular-lazy-module-duplicate-provider-instance
description: Diagnose a service meant to be an app-wide singleton getting a separate, out-of-sync instance inside a lazy-loaded feature.
triggers: ["lazy loaded module gets new service instance", "singleton service not shared across lazy modules", "providedIn root not working lazy module", "state out of sync between lazy feature and rest of app"]
permissions: ["READ"]
---

## Symptom
A service that's supposed to be a single app-wide instance -- holding
shared state, a cache, or a live connection -- turns out to have a
different instance, with out-of-sync state, inside a lazy-loaded feature
compared to the rest of the app.

## Likely causes
1. **The service is listed in the lazy-loaded `NgModule`'s (or a lazy
   standalone route's) own `providers:` array**, creating a new,
   module-scoped instance that shadows the app-wide one -- Angular's
   hierarchical injector resolves to the nearest provider, not
   automatically the root one.
2. **A "Core"/"Shared" module that itself provides the service is
   imported by more than one lazy-loaded feature module** -- each lazy
   chunk is loaded and executes that module's provider registration
   independently, in its own injector scope, producing one instance per
   feature instead of one for the whole app.
3. **The lazy module uses the older `loadChildren` module-based lazy
   loading, and a library's `forChild()` unexpectedly re-provides a
   service** that was only meant to be provided once, by the
   corresponding `forRoot()` call at the app root.
4. **The service is `providedIn: 'root'` in a library, but the lazy
   module also imports another module that redundantly re-declares the
   same provider**, common when a shared module is accidentally imported
   into both the root and a lazy feature.

## Diagnose
- Log a unique id (e.g. set once via `Math.random()` in the constructor)
  from the service's constructor; navigate into the lazy feature and log
  that id from a component there, then compare it against the id logged
  from a component elsewhere in the app that should share the same
  instance -- differing ids confirm duplicate instantiation.
- Search every `providers:` array in the codebase -- root
  `bootstrapApplication`, any `NgModule`, any lazy route's `providers:`
  -- for this service; more than one registration beyond its own
  `@Injectable({ providedIn: 'root' })` is the direct cause.
- Check whether a shared "Core"/"Shared" module providing the service is
  imported by more than one lazy-loaded feature module.

## Fix
- Remove the redundant `providers:` entry from the lazy module/route and
  rely solely on the service's `@Injectable({ providedIn: 'root' })` (or
  a single explicit registration in `bootstrapApplication`), so every
  part of the app -- eager or lazy -- resolves to the same root-injector
  instance.
- If a shared "Core" module is the source, ensure it's imported exactly
  once at the application root (a constructor guard that throws if
  already loaded is a common way to enforce this) rather than imported
  independently by multiple feature modules.
- When a library distinguishes `forRoot()` (registers providers, call
  once) from `forChild()`/a plain module import (declarations only, no
  provider registration), audit that every lazy feature module uses
  `forChild()` and only the root app module calls `forRoot()`.

## Pitfalls
- "Fixing" this with `providedIn: 'any'` misunderstands what that scope
  does -- it deliberately gives each lazy-loaded module its *own*
  instance by design, the opposite of a shared singleton; use
  `providedIn: 'root'` for genuinely app-wide singletons instead.
- Removing a provider from a lazy module without checking whether some
  part of that module actually relied on a fresh, feature-scoped instance
  (a legitimate pattern for feature-local state) can silently merge state
  across features that were supposed to stay isolated -- confirm the
  intended scope before consolidating providers.

## Verify
Repeat the unique-id logging check from Diagnose after the fix: navigate
into the lazy feature and confirm the id logged there matches the id
logged elsewhere in the app, and that a state change made from one
location (e.g. adding an item via a shared cart service) is immediately
visible from the other.
