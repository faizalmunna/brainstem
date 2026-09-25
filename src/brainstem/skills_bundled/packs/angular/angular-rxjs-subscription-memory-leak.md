---
name: angular-rxjs-subscription-memory-leak
description: Diagnose growing memory use and duplicate side effects caused by RxJS subscriptions that outlive the component that created them.
triggers: ["memory leak angular subscription", "observable not unsubscribed", "duplicate api calls after navigating back", "subscription outlives component angular"]
permissions: ["READ"]
---

## Symptom
Memory usage climbs over time and side effects duplicate (an API call
fires multiple times for one action, or a callback still runs after the
user navigated away from the component) after repeatedly navigating to
and away from the same route.

## Likely causes
1. **A `.subscribe()` in `ngOnInit` on a long-lived source** (a shared
   service's `Subject`, a WebSocket stream, `interval()`) with no matching
   teardown in `ngOnDestroy`, so each new component instance adds another
   permanently live subscription.
2. **Manual subscriptions to app-lifetime observables** like
   `Router.events` or a global store's state stream, whose lifetime isn't
   naturally tied to any one component's lifetime unless explicitly cut.
3. **Mixing the `async` pipe with a manual `.subscribe()` on the same
   source** -- the template's subscription is cleaned up automatically,
   but the manual one elsewhere in the class is not.
4. **A `.subscribe()` nested inside another `.subscribe()`** where only
   the outer subscription is torn down in `ngOnDestroy`, leaving the
   inner one alive and firing independently.

## Diagnose
- In Chrome DevTools' Memory tab, take a heap snapshot, navigate to and
  away from the component several times, take a second snapshot, and use
  "Comparison" filtered by the component's class name -- a retained count
  that keeps growing instead of returning to baseline confirms a leak.
- Search the component for every `.subscribe(` call and check each one
  against `ngOnDestroy` for a corresponding `.unsubscribe()`, a
  `Subscription.add()`, or a `takeUntil`/`takeUntilDestroyed` operator
  upstream of it.
- Temporarily log the component instance's identity from inside the
  subscribe callback; navigate away and re-trigger the source -- if the
  log still fires after leaving, that subscription outlived the instance.

## Fix
- Pipe every long-lived subscription through `takeUntilDestroyed()`
  (Angular 16+, called during construction or given an explicit
  `DestroyRef`) or a manual `destroy$` Subject completed in
  `ngOnDestroy` and referenced via `takeUntil(this.destroy$)`, so teardown
  is automatic and centralized instead of tracked per subscription.
- Prefer the `async` pipe in the template over a manual `.subscribe()`
  wherever the value is only needed for rendering -- Angular unsubscribes
  it automatically on component destruction.
- For a handful of subscriptions, collect them with a single
  `Subscription` object's `.add()` and call `.unsubscribe()` once in
  `ngOnDestroy`, reducing the chance of forgetting to tear down any one
  of them individually.

## Pitfalls
- Placing `takeUntil(this.destroy$)` *before* an inner `switchMap`/
  `mergeMap` that itself opens a never-completing subscription doesn't
  stop that inner subscription from leaking -- operator order matters;
  put `takeUntil` last, immediately before `.subscribe()`.
- Calling `takeUntilDestroyed()` outside an injection context (inside a
  `setTimeout` callback or a method invoked later rather than during
  construction) throws at runtime -- it needs either the implicit
  constructor injection context or an explicitly passed `DestroyRef`.

## Verify
Repeat the heap-snapshot comparison from Diagnose: navigate to and away
from the component several times, force garbage collection between
snapshots, and confirm the retained instance count for the component
class returns to baseline instead of accumulating.
