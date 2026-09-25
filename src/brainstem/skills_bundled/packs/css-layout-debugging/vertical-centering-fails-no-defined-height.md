---
name: vertical-centering-fails-no-defined-height
description: Fix flexbox or grid vertical centering that silently does nothing because the container collapses to its content height.
triggers: ["align-items center not working", "vertical centering not working", "flexbox center doesn't center vertically", "justify-content center works but align-items doesn't", "grid place-items center no effect"]
permissions: ["READ"]
---

## Symptom
`align-items: center` (flex) or `align-items`/`place-items: center`
(grid) is applied to a container and horizontal centering works fine
(`justify-content: center`), but vertical centering appears to do
nothing -- the child sits at the top of the container exactly as if no
centering rule existed.

## Likely causes
1. **The container has no defined height**, so it shrinks to exactly fit
   its content (the flex/grid item) -- there is no extra vertical space
   inside the container for centering to distribute, so `align-items:
   center` has nothing to do even though it's correctly applied.
2. **The container's height is defined but the item inside it is itself
   `align-self: stretch` (the flex/grid default)**, so the item fills the
   full cross-axis size and, again, there's no leftover space to center
   within, even though the container does have height.
3. **The parent of the flex/grid container is what actually needs the
   height** (a common nesting mistake: centering rules applied one level
   too high or too low relative to which element the height lives on).
4. **`height: 100%` is used but an ancestor in the chain up to `html`
   doesn't have an explicit height**, so the percentage resolves to `0`
   or `auto` instead of the expected viewport-relative size -- percentage
   heights require every ancestor up the chain to have a defined height,
   not just the immediate parent.

## Diagnose
- In DevTools, select the flex/grid container and check its computed
  `height` -- if it matches the content's height almost exactly (no
  visible slack), the container has no real height to center within.
- Check the centered child's computed `align-self` -- if it reads
  `stretch` (not `auto`/`center`), the child is filling the cross axis
  rather than being centered in it.
- For `height: 100%` cases, walk up the ancestor chain in the Elements
  panel checking each one's computed height; the chain breaks at the
  first ancestor whose height is `auto` with no intrinsic content
  height forcing it.

## Fix
Give the flex/grid container an explicit height appropriate to the
layout -- a fixed value, `min-height: 100vh` for a full-viewport section,
or `height: 100%` only once every ancestor up to `html`/`body` has an
explicit height (or use the modern `height: 100dvh`/`100svh` for
viewport-relative sizing that also handles mobile browser chrome
correctly). If the container's height is intentionally content-driven and
can't be fixed, use `margin: auto` on the item itself in a flex container
(which flexbox honors for centering along both axes) instead of relying
on `align-items`, since `margin: auto` centers based on available space
without requiring the parent to already have surplus height for the
`align-items` calculation to distribute.

## Pitfalls
- Reaching for `height: 100vh` on the container as a blanket fix breaks
  layouts that need to grow taller than the viewport (long content gets
  clipped or forces double scrollbars) -- prefer `min-height` unless the
  section must be exactly one viewport tall.
- Setting `height: 100%` on every ancestor "just to be safe" can produce
  layouts that no longer grow with content at all, since every level is
  now locked to its parent's box instead of its own content -- only the
  ancestors that actually need to pass height down should get it.

## Verify
Inspect the container's computed height in DevTools and confirm it now
has visible slack beyond the child's own height, then confirm visually
that the child sits centered between the container's top and bottom edges
at multiple viewport sizes, not just the one it was checked at originally.
