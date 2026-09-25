---
name: icon-button-missing-accessible-name
description: Fix an icon-only button, like a close or search control, that a screen reader announces only as "button" with no name.
triggers: ["screen reader says just button", "icon button no accessible name", "button has no discernible text", "aria-label missing on icon button", "close button not accessible"]
permissions: ["READ"]
---

## Symptom
A button that visually contains only an icon (a magnifying glass for
search, an X for close, a hamburger for a menu, a trash can for delete)
gets announced by a screen reader as just "button" with no indication of
what it does, forcing the user to guess or explore surrounding context.
Lighthouse/axe flag it as "Buttons must have discernible text." Sighted
users never notice because the icon itself communicates the action
visually.

## Likely causes
1. **The button contains only an `<svg>` or icon font glyph with no text
   content and no `aria-label`** -- the accessible name computation
   algorithm falls back through several sources (text content, `aria-
   labelledby`, `aria-label`, `title`) and finds nothing usable when
   the only child is a graphic with no text alternative of its own.
2. **The icon is an `<img>` with an empty or missing `alt` attribute**,
   or the SVG has a `<title>` element that isn't correctly wired for
   the accessible name computation, so the image contributes no text
   even though visually it's clearly informative in this context.
3. **A tooltip shows the label visually on hover**, giving the false
   impression the button is labeled, but the tooltip is CSS-only
   (shown via `:hover`) and not exposed to the accessibility tree at
   all -- it helps sighted mouse users exclusively.
4. **A wrapping `<span class="sr-only">` label was added but placed
   outside the `<button>` element**, or the button has `aria-
   hidden="true"` on an ancestor by mistake (common when a whole icon-
   button group is wrapped in a decorative container), so the label
   text exists in the DOM but isn't actually associated with or exposed
   for that control.

## Diagnose
- Inspect the button in the browser's Accessibility panel (Chrome/Edge
  DevTools "Accessibility" tab, or Firefox's Accessibility Inspector)
  and check the computed "Name" field -- an empty or missing name
  confirms the bug independent of what's visually shown.
- Run axe DevTools or Lighthouse; both directly flag "Buttons do not
  have an accessible name" and list the offending elements.
- Turn on a screen reader and Tab to the button -- if it announces just
  "button" with no descriptive text, the name computation is failing.
- If an `aria-label` is present but still not announced, check for an
  ancestor with `aria-hidden="true"` or `role="presentation"` that
  removes the whole subtree from the accessibility tree despite the
  label being technically there in markup.

## Fix
Give every icon-only interactive control an accessible name through one
of the standard mechanisms, chosen for maintainability rather than
whichever is fastest to type: `aria-label="Close dialog"` directly on
the `<button>` is simplest for a single static label; `aria-labelledby`
referencing existing visible text elsewhere is better when a similar
label already exists on the page and you want to avoid duplicating and
maintaining two copies of the same string; for SVG icons, an inline
`<title>` element inside the `<svg>` works if the icon is used stand-
alone outside a button context. Keep the label text action-specific and
current -- "Close dialog," not just "Close" or worse "Icon" -- and
update it if the button's behavior is contextual (e.g. "Expand
section" vs. "Collapse section" depending on toggle state, via `aria-
expanded` plus a corresponding label change or a single label like
"Toggle section" that doesn't need to change).

## Pitfalls
- Adding a visual CSS tooltip (`title` attribute or a custom hover
  popup) and assuming that satisfies the requirement -- the native
  `title` attribute is inconsistently exposed to screen readers and
  isn't a substitute for `aria-label`; a custom CSS-only tooltip isn't
  exposed at all.
- Setting `aria-label` to something generic and unhelpful ("icon",
  "button") just to silence the automated scanner, which passes the
  automated check but still leaves screen reader users without real
  information about the action.
- Applying `aria-hidden="true"` to the icon `<svg>` inside the button
  without adding a label to the button itself -- this correctly hides
  the *decorative* icon glyph from being separately announced, but the
  button as a whole still needs its own name.

## Verify
Inspect the button in the browser's Accessibility panel and confirm the
computed accessible name matches the button's actual action, then Tab
to it with a screen reader running and confirm it announces that name
(not just "button") along with the role.
