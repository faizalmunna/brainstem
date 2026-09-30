---
name: cypress-viewport-size-default-differs-in-ci
description: A Cypress test passes locally but fails in CI because the effective browser viewport size differs between the two environments, changing what is visible or how responsive layout renders.
triggers: ["cypress test fails only in ci viewport", "element not visible in ci but visible locally", "cypress responsive layout different in ci", "viewport size mismatch cypress"]
permissions: ["READ"]
---

## Symptom

A Cypress test that clicks or asserts on an element fails in CI with an
error indicating the element isn't visible or is covered by another
element, while the exact same test passes reliably when run locally
(interactively or headlessly) on a developer's machine.

## Likely causes

- **No explicit `viewportWidth`/`viewportHeight` is configured**, so the
  test relies on Cypress's default viewport, which may differ from the
  size a developer's local Cypress runner window happens to be sized to
  when running interactively.
- **A CI configuration overrides the viewport differently than local
  config** (a different `cypress.config.js` used in CI, or environment-
  specific overrides), producing a genuinely different effective viewport
  even though both claim to use "the default."
  causing a responsive breakpoint to trigger differently between the two.
- **The application's responsive layout hides or repositions an element
  at a specific breakpoint**, and the CI viewport happens to fall on the
  other side of that breakpoint from the local viewport.
- **A scrollable container's visible area differs by viewport size**, so
  an element that's "visible" in the DOM is outside the visible scroll
  area at the CI viewport size, which Cypress correctly reports as not
  actionable.

## Diagnose

1. Explicitly log the actual effective viewport size at the start of the
   failing test in both environments (`Cypress.config('viewportWidth')`/
   `viewportHeight`) to confirm whether they actually differ, rather than
   assuming.
2. Reproduce locally by explicitly setting the viewport to the CI value
   (`cy.viewport(width, height)` or the CI's configured value) and confirm
   the failure reproduces outside of CI, isolating viewport size as the
   actual variable.
3. Check the application's CSS for responsive breakpoints near the
   viewport width in question, to identify which specific breakpoint is
   causing the layout difference.
4. Check both the local and CI Cypress configuration files/environment
   variables for any viewport-related settings that might differ,
   including ones inherited from a shared CI Docker image's defaults.

## Fix

Set `viewportWidth`/`viewportHeight` explicitly in the Cypress
configuration (or per-test via `cy.viewport()` where a specific test
needs a specific breakpoint) so the test always runs at a known,
intentional size regardless of environment defaults -- removing the
"default" ambiguity is the core fix. For tests specifically meant to
verify responsive behavior at a particular breakpoint, use
`cy.viewport()` explicitly within the test to assert that exact
breakpoint's behavior, rather than relying on whatever the ambient
default happens to be.

## Pitfalls

Don't pick an arbitrary large viewport just to make elements "always
visible" and avoid the failure -- that can mask a real responsive-design
bug that would affect actual users at smaller/different viewport sizes.
If the application is meant to support a range of viewports, test at a
deliberately chosen representative set of sizes (e.g. a common mobile,
tablet, and desktop width) rather than picking whichever one happens to
make the current test pass.

## Verify

Run the test suite with the explicit viewport configuration in both
local and CI environments and confirm consistent results. Additionally,
run the suite once at a couple of the application's actual supported
breakpoints (if responsive behavior is a real requirement) to confirm the
element/interaction under test genuinely works at each, not just at
whichever single size was chosen to fix this specific flake.
