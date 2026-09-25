---
name: angular-async-guard-navigation-timing
description: Diagnose a route guard that inconsistently allows or blocks navigation because of async auth-state timing, especially right after a hard refresh.
triggers: ["route guard blocks navigation unexpectedly", "canactivate guard timing issue", "auth guard fails on page refresh angular", "async guard race condition angular router"]
permissions: ["READ"]
---

## Symptom
A route guard (`CanActivate`/`CanMatch`) returning an `Observable<boolean>`
or `Promise<boolean>` sometimes lets navigation through when it shouldn't,
or blocks it when it shouldn't, inconsistently -- most often right after
login/logout or on a hard page refresh of a protected route.

## Likely causes
1. **The guard reads auth state that hasn't finished initializing yet**
   on a hard refresh (e.g. a token-refresh HTTP call still in flight, or
   an async `APP_INITIALIZER` not yet resolved), so it evaluates against
   a default/placeholder value instead of the real one.
2. **The guard's observable never completes** -- returning a
   `BehaviorSubject` directly instead of piping it through `take(1)` --
   so the router either waits indefinitely or reacts to a later emission
   after navigation has already proceeded, depending on Angular version.
3. **The value the guard checks is set by a side effect inside the same
   observable chain the guard is evaluating** (a `tap` that flips the
   auth flag as part of the very check reading it), creating a race
   between when it's read and when it's set.
4. **Multiple guards on the same route implicitly assume an execution
   order** (one guard assumes another already refreshed the token) that
   isn't actually guaranteed by the router for that combination of guard
   types and route levels.

## Diagnose
- Log the current auth-state value with a timestamp at the very top of
  the guard function and again immediately before its `return`; reproduce
  the hard-refresh case and compare against a log placed in the
  token-refresh response handler to see which resolves first.
- Check whether the guard's returned observable completes: pipe it
  through `finalize(() => console.log('guard stream completed'))`
  temporarily and confirm that log fires.
- In the Network tab, check ordering on a hard refresh: does the
  auth-check/token-refresh HTTP call resolve before or after the guard
  evaluates?
- Confirm whether `provideAppInitializer`/`APP_INITIALIZER` is actually
  configured to await the auth-state-loading operation before the
  router's initial navigation runs, if the app depends on that.

## Fix
- Make the guard wait for a definitively resolved auth state rather than
  a possibly-still-loading one: pipe the auth stream through
  `filter(state => state !== 'loading')` before `take(1)`, so the guard
  only ever evaluates against a settled value, not a placeholder.
- Always terminate the guard's observable with `take(1)` (or use
  `firstValueFrom` for a promise-based guard) so the router receives
  exactly one boolean/`UrlTree` and never hangs on or reacts to a later
  emission.
- Ensure async initialization the guard depends on is awaited via
  `APP_INITIALIZER`/`provideAppInitializer` before the initial navigation
  runs, so a hard refresh can't race the guard against app startup.
- If ordering between guards genuinely matters, make the dependency
  explicit -- have the second guard itself await or trigger the first's
  prerequisite state rather than relying on execution order.

## Pitfalls
- Adding `take(1)` to a stream that hasn't reached its meaningful value
  yet just makes the guard resolve confidently with the *wrong*
  (default/loading) value instead of hanging -- it trades "never
  resolves" for "resolves wrong"; the `filter` step above is what
  actually fixes correctness, not `take(1)` alone.
- Making one guard depend on a value a sibling guard or resolver sets via
  a side effect assumes an execution-order guarantee the router doesn't
  always provide across guard types and route levels -- verify against
  the Angular Router documentation for the version in use rather than
  assuming.

## Verify
Log in, then hard-refresh (full page reload, not an in-app link) on a
protected route several times in a row, confirming the guard consistently
allows access each time; separately, log out and immediately attempt to
navigate to a protected route via a stale bookmark or the back button,
confirming it's blocked every time, not just most of the time.
