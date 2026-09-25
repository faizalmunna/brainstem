---
name: focus-indicator-removed-outline-none
description: Fix keyboard focus that becomes invisible after CSS removes the default outline from buttons, links, or inputs without a replacement.
triggers: ["outline none removed focus indicator", "cant see keyboard focus", "focus ring missing after css reset", "no visible focus state", "css reset removed outline accessibility"]
permissions: ["READ"]
---

## Symptom
A keyboard-only or low-vision user tabs through a page and has no
visual way to tell which element currently has focus -- the page looks
identical whether focus is on the first button or the last link.
Nothing crashes and nothing is announced wrong to screen readers (this
is a purely visual problem for sighted keyboard users), but it makes
the page effectively unusable without a mouse, since there's no way to
confirm where an Enter or Space press would take effect. It commonly
appears right after a CSS reset, a new component library adoption, or
a designer request to "remove that ugly blue box around buttons."

## Likely causes
1. **A global CSS reset or normalize stylesheet sets `outline: none`
   (or `outline: 0`) on all interactive elements** as part of "cleaning
   up" default browser styling, with no compensating focus style added
   anywhere else in the stylesheet.
2. **A component library's default button/link styles set `outline:
   none` specifically to remove the focus ring for mouse clicks** (a
   legitimate goal -- most users find a focus ring after a mouse click
   visually noisy) **but doesn't use `:focus-visible` to distinguish
   that case from keyboard focus**, so it removes the indicator for
   keyboard users too, not just mouse clickers.
3. **A custom focus style was added, but it's too subtle to actually
   be visible** -- a 1px border color change with insufficient contrast
   against the background, or a box-shadow that's clipped by a parent's
   `overflow: hidden`, so it exists in code but isn't perceivable in
   practice.
4. **Focus styles were removed specifically to fix a visual bug** (the
   outline appearing on click and looking "broken" against a custom
   button design) as a quick fix, without revisiting it once the
   underlying visual conflict could have been solved differently.

## Diagnose
- Tab through the page from the top and watch for any visible change
  (ring, border, background, underline) as focus moves between
  elements -- if nothing visibly changes on some or all elements,
  that's the bug directly.
- Search the CSS for `outline: none`, `outline: 0`, or `outline:
  transparent` applied to interactive elements or via a wildcard/reset
  selector, and check whether any `:focus` or `:focus-visible` rule
  supplies a replacement.
- If a focus style exists, verify its actual contrast against the
  adjacent background meets WCAG 2.2's 3:1 non-text contrast
  requirement for focus indicators, using a contrast checker on the
  indicator color against what's directly behind/around it.
- Check for a clipping ancestor (`overflow: hidden` or `overflow:
  auto` on a parent) that could be cutting off a box-shadow-based focus
  ring that's actually present in the DOM/CSS but invisible.

## Fix
Never remove the focus indicator without providing a replacement in the
same change -- treat `outline: none` on an interactive element as
requiring a paired `:focus` (or better, `:focus-visible`) rule with a
clearly visible alternative (a high-contrast outline, box-shadow ring,
or background/border change) in the same commit. Use `:focus-visible`
specifically to solve the "ugly ring after a mouse click" complaint
correctly: it lets browsers suppress the indicator for pointer-
initiated focus while still showing it for keyboard-initiated focus, so
designers get what they actually wanted (no ring after clicking) without
removing it for the users who depend on it. Make the replacement
indicator's contrast and thickness deliberate design decisions verified
against WCAG 2.2's non-text contrast criterion, not whatever a
component library ships by default, since many default focus styles are
themselves too subtle.

## Pitfalls
- Using `:focus` instead of `:focus-visible` for the replacement style
  reintroduces the exact "ring shows after every mouse click" complaint
  that motivated removing the outline in the first place, leading right
  back to another attempt to remove it.
- Restoring a focus indicator but styling it as a subtle 1px color
  change (matching brand aesthetics) that fails the 3:1 non-text
  contrast requirement passes a quick visual check by someone who knows
  where to look, while remaining effectively invisible to the users who
  need it.
- Fixing it globally by re-adding `outline: revert` or the browser
  default only on `<button>`/`<a>` can miss custom interactive elements
  (`role="button"` divs, custom dropdown triggers) that also had their
  outline removed by the same reset and need the same explicit
  treatment.

## Verify
Tab through every interactive element on the affected page or component
and confirm each one shows a clearly visible focus indicator, then
click (rather than Tab to) a few of the same elements with a mouse and
confirm the indicator does not appear on click if `:focus-visible` was
used, and check the indicator's color contrast against its background
meets at least 3:1.
