---
name: flex-children-not-shrinking-below-content
description: Fix flex items that refuse to shrink below their content's intrinsic width, causing overflow or broken layout on narrow viewports.
triggers: ["flex item overflows container", "text pushes out of flexbox", "flex child won't shrink", "flexbox overflowing on mobile", "long word breaks flex layout"]
permissions: ["READ"]
---

## Symptom
A flex row that fits fine on wide screens suddenly overflows its container
or breaks out horizontally on a narrow viewport -- one child (often one
holding text, an image, or a `<pre>`/code block) refuses to shrink past
its content's natural width even though `flex-shrink` is set and the
container is narrower than the combined content width.

## Likely causes
1. **The default `min-width: auto` on flex items.** By spec, a flex
   item's automatic minimum size is the size of its content (not `0`),
   so `flex-shrink` can shrink the item down to its content's intrinsic
   width but never below it -- long unbreakable text, a wide image, or a
   fixed-width child inside it sets that floor.
2. **An image or other replaced element inside the flex child has no
   `max-width: 100%`**, so its natural pixel width becomes the content's
   intrinsic width that `min-width: auto` locks in.
3. **Long unbroken strings (URLs, filenames, tokens)** with no
   `overflow-wrap`/`word-break`, so the "content size" the browser
   measures is the entire unbroken string's width.
4. **`flex-shrink: 0` set intentionally on a sibling** (e.g. to keep an
   icon or label a fixed size) which is fine on its own, but leaves the
   *other* item to absorb 100% of the shrink -- if the numbers don't add
   up, the other item still hits its own content-based floor first.

## Diagnose
- In DevTools, select the overflowing flex child and check the computed
  `min-width` -- if it shows `auto` (not `0`) that's the default floor
  the spec applies.
- Resize the viewport in DevTools' responsive mode while watching which
  child's right edge stays pinned past the container boundary; that's the
  one whose content is setting the floor.
- Check for a `<img>`, `<svg>`, or fixed-`width` child inside the
  overflowing flex item, and for unbroken text strings (paths, emails)
  using the Elements panel's box model overlay to see the actual content
  width vs. the container width.

## Fix
Set `min-width: 0` (or `min-height: 0` in a column flex context) on the
flex item that needs to shrink past its content -- this explicitly
overrides the automatic content-based minimum the spec assigns, letting
`flex-shrink` and `overflow` (e.g. `overflow: hidden` + `text-overflow:
ellipsis`) take over instead of the browser refusing to shrink further.
Combine with `max-width: 100%` on any image/media inside so the replaced
element doesn't reintroduce a wide intrinsic size, and `overflow-wrap:
break-word` (or `word-break: break-all` for things like long URLs) so
long unbroken strings can actually wrap instead of forcing width.

## Pitfalls
- Setting `min-width: 0` globally on every flex item "just in case" can
  hide layouts that genuinely need a minimum readable width (e.g. a
  sidebar column shrinking to unreadably narrow) -- apply it to the
  specific item that should truncate/wrap, not the whole row.
- Adding `overflow: hidden` without `min-width: 0` does nothing here,
  because the item never actually shrinks small enough for the overflow
  to kick in -- the two have to be paired.

## Verify
Resize the viewport down to the narrowest supported breakpoint (or use
DevTools device toolbar at the smallest target width) and confirm the
previously-overflowing child now shrinks, truncates, or wraps within the
container instead of pushing the layout wider than the viewport.
