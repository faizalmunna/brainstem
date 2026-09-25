---
name: custom-checkbox-not-keyboard-operable
description: Fix a custom checkbox or radio button built from a styled div that a keyboard user cannot focus, toggle, or announce correctly.
triggers: ["custom checkbox not keyboard accessible", "div checkbox doesn't work with keyboard", "can't tab to checkbox", "space bar doesn't toggle checkbox", "custom radio button screen reader"]
permissions: ["READ"]
---

## Symptom
A custom-styled checkbox or radio button (built as a `div` or `span`
with CSS to look like a checked/unchecked box, often to escape native
`<input>` styling limitations) can be clicked with a mouse to toggle,
but a keyboard user tabbing through the form skips right over it --
it's simply not reachable. Or it is reachable but pressing Space or
Enter does nothing. A screen reader user who does land on it hears
nothing indicating it's a checkbox or its current checked state.

## Likely causes
1. **The element is a non-interactive tag (`div`, `span`) with only a
   `click` handler and no `tabindex`** -- browsers don't include
   non-form, non-anchor elements in the natural tab order regardless of
   whether they have a click handler, so keyboard users can never focus
   it to begin with.
2. **`tabindex="0"` was added so it's focusable, but no keydown handler
   exists for Space (and Enter, for radios in some patterns)** -- mouse
   click events don't fire from keyboard activation on non-native
   elements the way they do on real `<button>`/`<input>` elements, so
   focusing the element and pressing Space silently does nothing.
3. **No ARIA role or state at all** (`role="checkbox"` plus `aria-
   checked`, or `role="radio"` plus `aria-checked` within a `role=
   "radiogroup"`) -- even a perfectly keyboard-operable custom widget is
   invisible to screen readers as a form control without these, since
   there's no native semantics to fall back on.
4. **A hidden native `<input type="checkbox">` is used underneath for
   semantics/form submission, but it's visually hidden with `display:
   none` instead of an accessible-hiding technique**, which removes it
   from the accessibility tree and the tab order entirely -- defeating
   the purpose of having it there.

## Diagnose
- Tab through the form from the top and count whether the custom
  checkbox/radio ever receives visible focus -- if it's skipped
  entirely, it's not in the tab order.
- If it is focusable, press Space (or Enter) while it has focus and
  confirm the checked state actually toggles, not just responds to a
  mouse click.
- Inspect the element in devtools for `role`, `aria-checked`, and (for
  radios) whether it's grouped correctly under `role="radiogroup"` with
  only one member reachable via Tab and the rest reachable via arrow
  keys (the native radio-group keyboard pattern).
- If a hidden native input backs the custom visual, check its CSS: `
  display: none` or `visibility: hidden` removes it from the
  accessibility tree, whereas the standard visually-hidden pattern
  (clip/absolute positioning with zero size, not display/visibility)
  keeps it accessible while visually replacing it with the styled
  sibling.

## Fix
The most reliable fix is to keep a real native `<input type="checkbox">`
or `<input type="radio">` in the DOM for actual semantics, keyboard
behavior, and form submission, visually hidden using the standard
screen-reader-only technique (absolutely positioned, 1px, clipped --
not `display:none`), and layer the custom-styled visual indicator next
to or over it using a `<label>` wrapping both (so clicking the visual
also toggles the real input natively) with CSS that reads the input's
`:checked` state to style the visual sibling. This gets keyboard
operability, correct screen reader announcement, and form submission
for free from the browser instead of reimplementing all three. Only
build a fully custom `role="checkbox"`/`role="radio"` widget from a
non-form element when there's a specific reason a native input can't be
used at all, and in that case implement the complete contract:
`tabindex="0"`, `role="checkbox"` with `aria-checked` kept in sync on
every toggle, and a keydown handler for Space (checkboxes) or arrow
keys within a `radiogroup` (radios) that calls the same toggle logic as
the click handler.

## Pitfalls
- Adding `role="checkbox"` and `aria-checked` to a `div` but forgetting
  the keydown handler for Space makes it screen-reader-announce
  correctly while still being completely unusable by sighted keyboard-
  only users, which is easy to miss if testing is screen-reader-only.
- Wrapping the hidden native input and visual indicator in a `<label>`
  but also adding a separate `onClick` handler to the visual `div` can
  cause a double-toggle (the label's native association fires once,
  the manual handler fires again), flipping the checkbox back to its
  original state on every click.
- For radio groups, implementing Tab to move between individual radios
  (rather than arrow keys within the group, with only one Tab stop for
  the whole group) breaks the standard OS-level expectation and can
  make the group unusable with assistive tech that relies on that
  convention.

## Verify
Tab to the control from the preceding field, confirm it receives visible
focus, press Space (or arrow keys for a radio group) and confirm the
checked state toggles and stays in sync between the visual indicator and
the underlying value, then confirm with a screen reader that it
announces as "checkbox, checked/unchecked" (or "radio button, N of M")
with the correct current state.
