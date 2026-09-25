---
name: playwright-locator-strategy
description: Choose robust Playwright locators that survive UI refactors, instead of brittle CSS/XPath selectors coupled to markup structure or styling.
triggers: ["selector breaks after refactor", "brittle locator", "css selector fragile", "xpath selector maintenance", "which locator to use playwright"]
permissions: ["READ"]
---

## Symptom
Tests break after a purely visual/structural change (a class name change,
a wrapper `<div>` added, a CSS framework migration) that didn't change
what the page actually does or looks like to a user -- the locator was
coupled to implementation details of the markup, not to something stable.

## Likely causes
1. **CSS selectors keyed on utility/framework class names**
   (`.MuiButton-root`, `.flex.items-center.gap-2`) that change whenever
   styling is refactored, even though the button itself didn't change.
2. **XPath or CSS selectors keyed on DOM structure/position**
   (`div > div:nth-child(3) > span`), which breaks the moment a wrapper
   element is added or the layout is restructured.
3. **Selecting by visible text in a locale-dependent or frequently-
   copy-edited string**, breaking on translation or minor wording tweaks
   unrelated to the element's function.
4. **No `data-testid`/accessible attributes added to custom components**,
   forcing tests to fall back to fragile structural selectors because
   there's no stable hook.

## Diagnose
- For a newly-broken locator, check what changed: if it's a class name,
  DOM nesting, or styling-only change with no change to the element's
  role/function/visible purpose, the locator was coupled to the wrong
  thing.
- Audit the test suite for selector patterns: heavy use of `.locator('.
  some-class')` or `page.locator('xpath=...')` versus Playwright's
  role/label/text-based locators.

## Fix
- Prefer Playwright's built-in accessible locators in this priority
  order: `getByRole` (with an accessible name), `getByLabel`,
  `getByPlaceholder`, `getByText` (for genuinely stable, user-facing
  text), then `getByTestId` as an explicit escape hatch for elements with
  no natural accessible identity (a decorative icon button, a complex
  custom widget) -- add a `data-testid` to the component specifically for
  this rather than reaching for a structural selector.
- Prefer locating relative to a stable landmark (`page.getByRole('region',
  { name: 'Checkout' }).getByRole('button', { name: 'Pay' })`) over deep
  structural paths, so the locator survives internal restructuring of
  that region.
- When a component genuinely lacks an accessible name (common with icon-
  only buttons), that's also an accessibility gap worth flagging/fixing
  in the component itself, not just a testing inconvenience to work
  around.

## Pitfalls
- Defaulting to `data-testid` everywhere avoids the class-name/structure
  brittleness but throws away the side benefit of role/label-based
  locators: they double as an accessibility check, since a test using
  `getByRole('button', { name: 'Submit' })` only passes if the element is
  actually exposed to assistive tech that way. Use role/label first, and
  `data-testid` specifically where there's truly no accessible identity.
- Locating by exact visible text on strings the product/content team
  edits frequently (marketing copy, tooltips) creates maintenance churn
  unrelated to actual functional changes -- prefer a stable attribute or
  a partial/regex match on the stable part of the text where the text
  itself isn't the thing under test.

## Verify
Make a purely cosmetic change (rename a CSS class, restructure a wrapper
`<div>`, run a CSS-framework migration codemod) without changing any
element's role, label, or visible text, and confirm the test suite still
passes -- if it doesn't, the locators are still coupled to markup, not
behavior.
