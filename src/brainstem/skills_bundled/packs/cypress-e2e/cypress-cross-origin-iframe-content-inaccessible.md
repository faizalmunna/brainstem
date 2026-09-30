---
name: cypress-cross-origin-iframe-content-inaccessible
description: A Cypress test cannot interact with content inside an iframe or a redirected third-party page because the content lives on a different origin than the top-level test.
triggers: ["cypress cannot access iframe content", "cross origin error cypress", "cypress cy.origin needed", "third party checkout iframe cypress test"]
permissions: ["READ"]
---

## Symptom

A Cypress test that needs to interact with content inside an `<iframe>`
(a payment widget, an embedded third-party form) or that follows a
redirect to a different domain (an OAuth login page, a payment
processor) fails with an error about cross-origin access, or simply
can't find elements that are visibly present in the browser.

## Likely causes

- **The iframe's content is served from a different origin** (protocol,
  domain, or port) than the page under test, and Cypress's default
  command execution context can't reach across that boundary without
  explicit same-origin-policy-aware handling.
- **A flow navigates the top-level page itself to a different origin**
  (an OAuth provider's login page, a payment gateway's hosted page)
  without using `cy.origin()` to explicitly hand off command execution to
  that origin's context.
- **A third-party script inside the iframe loads asynchronously**, so
  even correctly-scoped commands targeting the iframe fail because they
  run before the iframe's content has actually rendered.
- **The test was written assuming same-origin behavior** because it
  worked in an older Cypress version or a different testing tool with
  looser cross-origin restrictions, and wasn't updated for Cypress's
  origin-aware command model.

## Diagnose

1. Confirm the actual origin of the iframe's `src` or the redirected
   page's URL, and compare it against the origin of the page the test
   started on -- any difference in protocol, domain, or port is a
   cross-origin boundary Cypress must be told about explicitly.
2. Check the Cypress version and its documented approach to cross-origin
   content (`cy.origin()` for full page navigations, and note that
   arbitrary third-party iframe content may remain fundamentally
   untestable if it doesn't cooperate with test automation at all).
3. For iframe content specifically, check whether the iframe is same-
   origin (in which case `.its('0.contentDocument.body')`-style access
   patterns work) or cross-origin (which needs a different approach or
   may not be directly accessible at all).
4. Check whether the iframe's content is fully loaded before the test
   attempts to interact with it, independent of the origin issue.

## Fix

For a full-page navigation to a different origin (an OAuth flow, a
hosted payment page), wrap the interaction in `cy.origin()`, which
explicitly tells Cypress to execute the enclosed commands in that origin's
browser context. For same-origin iframes, access the iframe's document
directly rather than treating it as an opaque black box. For genuinely
cross-origin third-party iframes that don't expose a testable API and
aren't under the team's control (a real embedded payment widget, for
example), the realistic fix is often to *not* test through the real
third-party UI in E2E tests at all -- stub the third-party's response at
the network level via `cy.intercept()` for most test scenarios, and
reserve a small number of true end-to-end tests against the real
third-party sandbox environment for a separate, lower-frequency
verification pass.

## Pitfalls

Don't disable Cypress's origin-related protections (via configuration
flags meant for narrow, specific cases) as a blanket workaround --
that can mask real cross-origin issues the app itself would hit for real
users, not just the test. Also don't assume `cy.origin()` alone solves
every cross-origin case: some third-party embeds are designed to resist
automation entirely (bot-detection, canvas fingerprinting) and no
Cypress configuration will reliably drive them the way stubbing at the
network boundary would.

## Verify

Run the test against the real (or sandboxed) third-party flow at least
once manually/interactively to confirm the `cy.origin()`-wrapped
interaction actually works end-to-end, then confirm the stubbed version
used for regular CI runs still exercises the app's own handling of the
third party's success/failure responses realistically.
