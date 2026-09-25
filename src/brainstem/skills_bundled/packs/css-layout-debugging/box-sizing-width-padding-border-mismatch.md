---
name: box-sizing-width-padding-border-mismatch
description: Fix an element rendering wider or narrower than its declared width because padding or border is added on top of it instead of included.
triggers: ["element wider than expected", "width plus padding overflows", "input wider than container", "box wider than set width", "percentage width plus padding breaks layout"]
permissions: ["READ"]
---

## Symptom
An element with an explicit `width` (often `100%` or a fixed value) ends
up visibly wider than its container once padding and/or a border are
added -- e.g. a form input styled with `width: 100%; padding: 10px;
border: 1px solid` overflows its parent by exactly the padding+border
amount, or a grid of boxes with equal declared widths ends up visibly
uneven once some have borders and others don't.

## Likely causes
1. **Default `box-sizing: content-box` is in effect**, under which
   `width` sets only the content area, and padding and border are added
   *on top of* that width rather than being included within it -- so
   `width: 100%` plus any padding/border is always wider than 100% of the
   parent.
2. **A CSS reset/normalize that sets `box-sizing: border-box` globally
   is missing or was scoped incorrectly** (e.g. applied only to `*` but
   overridden by a more specific selector, or not applied inside a
   shadow DOM / third-party widget that doesn't inherit the page's
   reset).
3. **Inconsistent `box-sizing` between sibling elements** -- some
   components (especially third-party ones, or older code predating a
   later-added reset) use `content-box` while the rest of the page uses
   `border-box`, producing visually uneven sizing between elements that
   otherwise share the same declared `width`.
4. **A width calculated in JS (`getBoundingClientRect`, `offsetWidth` vs
   `clientWidth`)** being applied back into a `width` CSS property without
   accounting for which box model is active, causing a compounding
   mismatch on re-render.

## Diagnose
- In DevTools, select the element and check the box-model diagram --
  it visually separates content/padding/border/margin regions and shows
  whether the declared `width` matches the content box or the full
  border box.
- Check the computed `box-sizing` value directly in the Styles/Computed
  panel; `content-box` is the browser default when no reset is applied.
- If a global reset exists, search for `box-sizing: border-box` in the
  stylesheet and confirm it's applied with a selector that actually
  covers the misbehaving element (including via `*`, `*::before`,
  `*::after`, and not overridden later by a more specific rule).

## Fix
Apply `box-sizing: border-box` -- ideally globally via a reset
(`*, *::before, *::after { box-sizing: border-box; }`) so `width`
consistently means the full rendered box including padding and border,
matching how most people intuitively expect sizing to work and matching
how flex/grid track sizing already treats items. For a one-off element
that can't take the global reset (embedded third-party widget, legacy
component with `content-box` baked into its own internals), explicitly
set `box-sizing: border-box` on just that component's root rather than
fighting it by subtracting padding/border from the `width` value by hand.

## Pitfalls
- Adding a global `box-sizing: border-box` reset late in a mature
  codebase can shift the rendered size of many existing elements at once
  if some layouts were unintentionally relying on `content-box` math --
  audit visually across key pages after introducing it, not just the one
  component that prompted the fix.
- Manually subtracting padding/border from a `width` value (`width:
  calc(100% - 22px)`) as a workaround instead of fixing `box-sizing` is
  brittle -- it breaks again the moment padding or border changes, since
  the magic number has to be updated everywhere it was hardcoded.

## Verify
Check the element's computed box-sizing is `border-box` and that its
rendered outer width (content + padding + border, visible in the
DevTools box-model diagram) now matches the intended `width` value
exactly, at both the fixed size and after resizing the container for any
percentage-based width.
