---
name: angular-standalone-component-missing-provider
description: Diagnose a NullInjectorError for a service that resolved fine under NgModules but breaks after migrating to standalone components.
triggers: ["NullInjectorError standalone component", "no provider for service after standalone migration", "standalone component missing provider", "provideX not called angular standalone"]
permissions: ["READ"]
---

## Symptom
A standalone component or service throws `NullInjectorError: No provider
for X` at runtime, even though the exact same service worked fine when
the app was built with `NgModule`s -- typically surfacing right after
migrating a feature (or the whole app) to standalone components and
`bootstrapApplication`.

## Likely causes
1. **The service was previously registered via an `NgModule`'s
   `providers` array** (including a library's `forRoot()`/`forChild()`
   pattern) that isn't imported anywhere in the standalone bootstrap or
   route config, so nothing registers it with an injector anymore.
2. **A standalone component imports another standalone component's
   `imports:` array expecting it to also carry over a provider** the way
   an `NgModule` implicitly re-exported providers to its consumers --
   standalone `imports:` only wires up declarables (components,
   directives, pipes), not services.
3. **The component is lazy-loaded via `loadComponent`**, and the provider
   was only ever registered in the eagerly-loaded root's
   `bootstrapApplication` `providers:` array in a way that isn't actually
   reachable from wherever it's now being resolved.
4. **A library's `forRoot()`-style static method was relied on for
   provider registration**, and the standalone migration only imported
   the library's standalone component/directive, dropping the modern
   `provideX()` function call that replaced `forRoot()`.

## Diagnose
- Read the `NullInjectorError`'s printed injector chain (e.g.
  `R3InjectorError(Standalone[...])`) -- it lists the exact path Angular
  walked, showing which injector (component-level, route-level, or root)
  failed to find the token.
- Check the service's `@Injectable()` decorator for `providedIn: 'root'`
  -- if present, it should resolve anywhere unless something registers a
  conflicting instance lower in the tree; if absent, it must be explicitly
  listed in a `providers:` array reachable from the injection point.
- Search the codebase for wherever this provider used to be registered
  before the migration (an `NgModule`'s `providers:`, or a `.forRoot()`
  call) and confirm an equivalent registration exists somewhere in
  `bootstrapApplication()`'s providers, a route's `providers:`, or the
  standalone component's own `providers:`.

## Fix
- Add the missing provider -- or the library's modern `provideX()`
  function, which is the standalone-era replacement for `forRoot()` in
  most Angular and third-party libraries -- to `bootstrapApplication`'s
  `providers:` for app-wide singletons, or to the relevant route's
  `providers:` for feature-scoped ones.
- For a service meant to be a global singleton, prefer
  `@Injectable({ providedIn: 'root' })` over manually listing it in
  multiple `providers:` arrays -- it removes the need to remember to wire
  it up per bootstrap/route and stays tree-shakeable.
- When migrating a library off `forRoot()`, check its changelog/docs for
  the standalone `provideX()` equivalent rather than assuming importing
  its standalone component alone also registers its providers.

## Pitfalls
- Adding the same provider to both `bootstrapApplication` and a lazy
  route's `providers:` "just to be safe" creates two separate instances
  of what was meant to be one singleton, silently breaking shared state
  between the eager and lazy parts of the app -- register a true
  singleton in exactly one place.
- Slapping `providedIn: 'root'` onto a service that was deliberately
  scoped per-feature (e.g. state meant to reset per lazy route) turns it
  into an unintended app-wide singleton, leaking state across features
  that were supposed to stay isolated.

## Verify
Reload the app and navigate to the route/component that threw the error,
confirming the `NullInjectorError` is gone; then, if the service is meant
to be a singleton, log from its constructor and confirm exactly one
instance is created for the whole app session, not one per navigation.
