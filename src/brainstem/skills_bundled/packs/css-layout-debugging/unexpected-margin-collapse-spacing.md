---
name: unexpected-margin-collapse-spacing
description: Explain unexpectedly large or missing vertical spacing between sibling or parent-child elements caused by CSS margin collapsing.
triggers: ["margin bigger than expected", "gap between elements too large", "margin not showing", "top margin ignored on div", "spacing doubles between sections"]
permissions: ["READ"]
---

## Symptom
Vertical space between two block elements is noticeably larger than
either element's own margin value (looks like the margins added
together when they shouldn't have, or one margin seems to have "leaked"
outside its container), or a margin set on a child appears to do nothing
and instead pushes the parent element itself down.

## Likely causes
1. **Adjacent sibling margin collapse**: a bottom margin on one block
   element and a top margin on the next sibling collapse into a single
   margin equal to the *larger* of the two (not their sum), which is
   correct spec behavior but reads as "my margin isn't being applied" to
   anyone expecting additive spacing.
2. **Parent-child margin collapse**: a child's top margin collapses
   through its parent when the parent has no border, padding, or
   established formatting context separating them, so the margin visually
   appears *above* the parent instead of pushing the child down inside it.
3. **Empty element margin collapse**: an empty block element (no content,
   no height, no border/padding) with both a top and bottom margin
   collapses those two margins into each other, producing a single gap
   that isn't obviously "two margins" at all.
4. **`overflow: hidden`, `display: flow-root`, or a border/padding
   already applied to the parent in an unrelated part of the layout**,
   which prevents collapse in a way that looks inconsistent between
   otherwise-similar components on the same page.

## Diagnose
- In DevTools, select each of the two elements involved and read the box
  model diagram's margin values -- if the visible gap equals the larger
  of the two margins rather than their sum, that confirms sibling
  collapse.
- For the "margin does nothing / parent moved instead" case, select the
  child and check whether the parent's rendered top edge shifted by the
  same amount as the child's margin -- that confirms parent-child
  collapse-through.
- Temporarily add `border: 1px solid red` (or any border/padding) to the
  parent in DevTools' style editor; if the layout suddenly changes and
  the margin now applies where expected, collapse-through was the cause.

## Fix
To stop a child's margin from collapsing through its parent, give the
parent a formatting context that blocks collapse: `display: flow-root`
is the modern purpose-built fix (unlike `overflow: hidden`, it has no
side effects on legitimate overflow), or any of border/padding on that
side, or `display: flex`/`grid` if the parent already needs to be a flex
or grid container. To stop unwanted sibling collapse, use only one side
of the pair (e.g. always space with `margin-bottom` and never also set
`margin-top` on the next element) so there is nothing to collapse against,
or use a `gap` property on a flex/grid parent instead of margins entirely,
since `gap` is never subject to collapsing.

## Pitfalls
- Reaching for `overflow: hidden` to block collapse-through is a common
  fix that works, but silently clips any child that legitimately needs to
  overflow (a dropdown, a negative-margin decorative element, a box-shadow
  on hover) -- prefer `display: flow-root` when there's no other reason
  the parent needs `overflow` set.
- Converting spacing to `gap` on a flex/grid container fixes collapse but
  changes behavior for any child that used a manually-tuned asymmetric
  margin (e.g. more space above a heading than below it) -- `gap` applies
  uniformly between items and won't reproduce asymmetric spacing without
  extra rules.

## Verify
Re-inspect the box model for both elements in DevTools and confirm the
rendered gap now matches the intended value (either the sum you expect
from `gap`, or the single margin you deliberately kept), and confirm the
parent's own top/bottom edges no longer shift when the child's margin
value is changed.
