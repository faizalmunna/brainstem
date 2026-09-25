---
name: cypress-intercept-alias-set-up-too-late
description: A Cypress test times out waiting on an aliased network request because the request already fired before cy.intercept() registered the alias.
triggers: ["cy.wait alias never called", "cypress intercept not matching request", "cypress timed out waiting for route", "intercept registered too late"]
permissions: ["READ"]
---

## Symptom

`cy.wait('@someAlias')` times out with an error like "no request ever
occurred," even though the network tab (or the app's actual behavior)
clearly shows the request happened and got a response -- the app
functions correctly, but the test can't find the request it's waiting on.

## Likely causes

- **`cy.intercept()` was registered after the action that triggers the
  request**, e.g. calling `cy.visit()` (which starts loading the page and
  its data requests) and only setting up the intercept afterward, missing
  the request entirely since Cypress can only intercept requests made
  after the interceptor is active.
- **The request fires on page load / component mount** rather than in
  response to a later user action, so any intercept set up inside the
  test body (after `cy.visit()`) is fundamentally too late for that
  specific request.
- **The intercept's URL/method matcher doesn't actually match the real
  request** (a subtly different path, query string, or HTTP method),
  which produces the same "alias never called" symptom as timing, but for
  a different reason -- always worth ruling out separately.
- **A cached response (browser cache, service worker) serves the request
  without it ever hitting the network layer Cypress intercepts at**, so
  from Cypress's perspective no matching request occurred even though the
  app clearly displayed the data.

## Diagnose

1. Move the `cy.intercept()` call to before `cy.visit()` (or before
   whatever action triggers the request) and see if the alias resolves --
   if it does, ordering was the issue.
2. Check the Cypress command log/network tab for the *actual* request
   URL/method that fired and diff it character-for-character against the
   intercept's matcher pattern.
3. Temporarily broaden the intercept matcher (e.g. intercept all requests
   to the API's base path) to confirm whether *any* interception fires at
   all, isolating whether the problem is timing or matching.
4. Check whether the app or browser might be serving the response from a
   cache/service worker rather than an actual network round-trip during
   this specific test scenario.

## Fix

Register every `cy.intercept()` needed for a page's initial load *before*
`cy.visit()` is called, since Cypress applies interceptors to requests
made after they're set up -- for a single-page app, this means
intercepting before the visit that triggers the app's initial data
fetches, not after. For requests triggered by a later user action (a
button click, a form submit), it's fine to set up the intercept anywhere
before that action, but keep the general habit of setting up intercepts
as early as possible in the test to avoid this class of ordering bug
entirely. Make matcher patterns as specific as necessary but no more --
overly specific matchers (exact query string order/values) are fragile to
harmless implementation changes.

## Pitfalls

Don't work around this by adding an arbitrary `cy.wait(ms)` before the
intercept setup to "give the page time" -- that doesn't fix the ordering
issue (the request may still fire before the wait completes, depending on
the app's actual load speed) and reintroduces timing-based flakiness.
Also don't disable browser caching or service workers globally just to
make one intercept-timing issue easier to test -- that changes the app's
real caching behavior under test, potentially hiding a different real bug
related to caching itself.

## Verify

Confirm `cy.wait('@someAlias')` resolves reliably across multiple runs,
including on a throttled network profile (Cypress supports simulating
slower connections), to confirm the fix isn't dependent on a fast local
network masking residual timing sensitivity. Check that the intercept's
matcher is specific enough to not accidentally also match an unrelated
request that happens to share a path prefix.
