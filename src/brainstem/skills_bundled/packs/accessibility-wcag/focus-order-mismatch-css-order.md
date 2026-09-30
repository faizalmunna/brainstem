---
name: focus-order-mismatch-css-order
description: Fix keyboard tab order that jumps around the screen unpredictably after elements are visually reordered with CSS flex or grid order.
triggers: ["tab order doesn't match visual order", "flex order breaks tab order", "css grid order keyboard navigation wrong", "tabbing jumps around screen", "visual order different from dom order"]
permissions: ["READ"]
---

## Symptom
Tabbing through a page moves the visible focus indicator in a
confusing, non-linear path -- jumping from the middle of the screen
back up to the top, skipping a column, or bouncing between visually
distant elements -- even though clicking through the same elements with
a mouse follows the expected left-to-right, top-to-bottom visual
layout. Sighted keyboard users lose track of where focus went; screen
reader users navigating linearly hear content in an order that doesn't
match what's on screen for anyone following along visually (e.g. a
sighted parent helping a low-vision user, or captions/live meeting
notes referencing "the field above").

## Likely causes
1. **CSS `order` (flexbox or grid) is used to visually reposition
   items without changing their DOM order** -- browsers always compute
   Tab order from DOM source order, never from the CSS-painted visual
   position, so `order` creates an intentional mismatch between what's
   seen and what's tabbed.
2. **CSS Grid placement (`grid-column`/`grid-row`, especially with
   named areas) visually rearranges a form's fields for a responsive
   layout**, but the underlying markup was written in a different
   sequence for markup convenience, producing the same visual/DOM
   divergence as `order`.
3. **Absolute/fixed positioning pulls an element far from its DOM
   position visually** (a positioned tooltip, a sidebar widget rendered
   at the end of the DOM but pinned visually near the top) without any
   corresponding adjustment to reading/tab order.
4. **A responsive layout reorders content differently per breakpoint**
   (mobile shows filters before results, desktop shows results before
   filters, achieved via `order` at different media query breakpoints)
   so the DOM order that was "close enough" at one breakpoint is wrong
   at another.

## Diagnose
- Tab through the page at the affected breakpoint and compare the path
  of the visible focus ring against the visual layout -- does it ever
  move backward or skip to a distant region instead of proceeding in
  reading order?
- Inspect the DOM tree order of the affected elements versus their
  rendered visual position -- a mismatch here (independent of any CSS
  layout tool) reproduces the bug's root cause directly.
- Check computed CSS for `order`, `grid-column`/`grid-row` with
  non-sequential values, or `position: absolute/fixed` on the elements
  involved.
- If the issue only shows at certain viewport widths, repeat the Tab-
  order check at each breakpoint where the layout's CSS changes.

## Fix
Treat DOM order as the source of truth for both reading order and tab
order, and use CSS purely for visual presentation: reorder the actual
markup to match the intended reading/tab sequence, then use `order` (or
grid placement) only for cases where the visual rearrangement is
genuinely presentation-only and doesn't change the logical relationship
between elements (e.g. swapping which of two already-independent,
non-sequential cards appears first, where either tab order reads
sensibly). When a layout fundamentally needs different visual sequences
at different breakpoints in a way that DOM order can't satisfy for
both, prefer restructuring the layout (e.g. using CSS Grid areas mapped
from a single sensible DOM order, rather than flipping `order` values
per breakpoint) or, as a last resort, accept and test that the DOM
order chosen serves the more content-critical breakpoint's reading
order, since DOM order is what every non-visual and keyboard user
experiences regardless of viewport.

## Pitfalls
- "Fixing" a bad tab order by manually re-assigning `tabindex` values
  (`tabindex="1"`, `tabindex="2"`, etc.) to force a specific sequence
  fights the browser's default order-management, is extremely fragile
  to future markup changes, and is explicitly called out by WCAG
  guidance as an anti-pattern versus fixing the underlying DOM order.
- Reordering the DOM to fix tab order can silently change which
  heading/landmark structure screen readers announce first, so re-check
  document outline and landmark navigation after moving elements, not
  just the visual layout.
- Fixing tab order at one breakpoint by changing DOM order can
  reintroduce the exact same mismatch at a different breakpoint if
  `order` is still being used elsewhere in the same component for
  responsive rearrangement.

## Verify
At each breakpoint the layout supports, tab through the affected region
and confirm the focus indicator moves in the same sequence a sighted
user would read the content visually, with no backward jumps or
skipped-then-returned-to elements; cross-check with a screen reader's
linear reading order to confirm it matches the visual layout too.
