---
name: modal-focus-trap-missing
description: Diagnose a modal dialog that lets keyboard and screen-reader users tab into the page behind it instead of trapping focus inside.
triggers: ["modal doesn't trap focus", "tab escapes modal", "focus goes behind dialog", "keyboard can reach page behind modal", "screen reader reads background content while modal open"]
permissions: ["READ"]
---

## Symptom
Opening a modal (a confirmation dialog, a settings panel, a cookie banner)
and pressing Tab repeatedly moves focus onto links, buttons, or form
fields in the page *behind* the modal, which visually still shows the
overlay/backdrop. A screen reader user hears content from the underlying
page being announced while the modal is supposedly the only active
surface. Pressing Escape may do nothing, or focus never lands inside the
modal in the first place when it opens.

## Likely causes
1. **The modal is rendered in the DOM without any focus management code**
   -- it's just a `position: fixed` overlay with a higher `z-index`, so it
   looks on top visually, but the DOM tab order is untouched and
   background elements remain focusable.
2. **No focus trap listener on Tab/Shift+Tab** -- the modal moves initial
   focus into itself correctly, but nothing intercepts Tab at the last
   focusable element to wrap back to the first (or Shift+Tab at the
   first to wrap to the last), so continued tabbing walks off the end of
   the modal's DOM subtree into whatever follows in document order.
3. **Background content isn't marked inert** -- neither `inert`,
   `aria-hidden="true"` on sibling containers, nor removing background
   elements from the tab sequence, so assistive tech and Tab navigation
   can both still reach it even if the trap partially works for some
   elements.
4. **The modal is portaled to the end of `<body>` but the trap logic
   assumes it's the last element** -- other scripts (analytics widgets,
   chat launchers) inject elements after it at runtime, giving the "last
   focusable element" logic a moving target it doesn't account for.

## Diagnose
- Open the modal, then press Tab repeatedly while watching the visible
  focus ring -- does it ever land on an element outside the modal's
  bounding box?
- In browser devtools, inspect the modal's container and its siblings:
  do the siblings have `inert` or `aria-hidden="true"` applied while the
  modal is open, or are they left fully in the accessibility tree?
- Run axe DevTools or Lighthouse's accessibility audit against the page
  with the modal open -- both flag "focusable content inside `[aria-
  hidden=true]`" or missing dialog focus management, but you must trigger
  the modal open state first since most scanners audit static DOM.
- Check whether `role="dialog"` (or `alertdialog`) and `aria-modal="true"`
  are present on the modal container; their absence means assistive tech
  has no signal this is a modal at all, independent of the Tab bug.

## Fix
Treat "trap focus" as three coordinated behaviors, not one: (1) move
focus into the modal when it opens (to the modal container, its heading,
or its first interactive control), (2) intercept Tab/Shift+Tab at the
modal's boundary so focus cycles within it, and (3) remove the rest of
the page from both the tab order and the accessibility tree while the
modal is open, using the native `inert` attribute on the background
root (or `aria-hidden="true"` plus `tabindex="-1"` on every background
focusable if `inert` isn't available). Prefer the browser's native
`<dialog>` element with `.showModal()` where it fits, since it provides
focus trapping and background inerting for free; when building a custom
modal, use a maintained primitive (Radix, Headless UI, react-aria's
`useDialog`/`FocusScope`) rather than hand-rolling the Tab-key
interception, because the edge cases (dynamically added trailing
elements, nested modals, elements that become non-focusable while
tabbing) are exactly what these libraries already handle. On close,
restore focus to the element that opened the modal, not to `<body>`.

## Pitfalls
- Setting `aria-hidden="true"` on `<body>`'s other children but forgetting
  to also add `tabindex="-1"` (or use `inert`) still leaves those
  elements keyboard-focusable even though they're hidden from the
  accessibility tree -- screen reader users are protected but keyboard-
  only sighted users can still tab into invisible/hidden content.
- Trapping focus but never returning it to the triggering element on
  close leaves keyboard users disoriented, dumped back at the top of the
  document or wherever focus happens to land by default.
- Hard-coding "first and last focusable element" once at modal-open time
  breaks if the modal's content changes after opening (e.g. an
  async-loaded list) -- recompute the boundary elements on each Tab
  press, or use a trap implementation that queries live.

## Verify
With the modal open, Tab through every element until you cycle back to
the first one without ever leaving the modal, then Shift+Tab from the
first element and confirm it wraps to the last. Confirm Escape closes
the modal and returns focus to the trigger button. Re-run the check with
a screen reader (NVDA or VoiceOver) active and confirm nothing outside
the modal is announced while it's open.
