---
name: grid-item-overflowing-track
description: Fix a CSS Grid item that overflows its column or row track instead of wrapping or shrinking to fit.
triggers: ["grid item overflows column", "grid child too wide for track", "content spills out of grid cell", "grid overflowing horizontally", "minmax not preventing overflow"]
permissions: ["READ"]
---

## Symptom
A grid item's content (long text, a wide table, a code block, an image)
spills out past the edges of its column track, sometimes pushing the
whole grid wider than its container or overlapping the next column,
even though the track is sized with `1fr` or a `minmax()` that should
constrain it.

## Likely causes
1. **The same implicit-minimum-size issue as flexbox**: a grid item's
   automatic minimum width/height defaults to its content size (`min-
   width: auto` / `min-height: auto`), so an `fr` track or `minmax(0,
   1fr)` track still can't shrink the item below its intrinsic content
   width unless that default is overridden on the item itself.
2. **A `minmax()` track using a non-zero minimum** (e.g. `minmax(200px,
   1fr)`) that is larger than the actual available space once other
   tracks and gaps are accounted for, forcing the grid to overflow rather
   than shrink that track further.
3. **A wide, non-wrapping child inside the grid item** (an image without
   `max-width: 100%`, a `<table>` without `table-layout: fixed`, a `<pre>`
   without `overflow-x: auto`) setting the content's intrinsic size
   independently of the grid track sizing.
4. **`grid-template-columns` using fixed px/em widths** that simply don't
   add up to the container width at the current viewport, which is a
   sizing-math bug rather than a shrink-behavior bug.

## Diagnose
- Enable the Grid overlay in Chrome or Firefox DevTools (click the grid
  badge next to the element, or the "Layout" panel's grid inspector) to
  see the actual computed track boundaries versus where the content
  visually extends.
- Check the overflowing item's computed `min-width`/`min-height` -- if it
  is `auto` rather than `0`, the content floor is the culprit.
- Read off the computed track sizes in the grid overlay and compare
  against the container's content-box width to see whether the `minmax()`
  minimums simply exceed available space (a math problem, not a shrink
  problem).

## Fix
For content that should wrap/truncate instead of forcing the track wider,
set `min-width: 0` (or `min-height: 0`) on the grid item itself, exactly
as with flexbox, and pair it with `minmax(0, 1fr)` on the track definition
so the track's own minimum doesn't independently force width. For tracks
sized with a hard pixel minimum that genuinely can't fit, either lower the
minimum, switch to `auto-fit`/`auto-fill` with `minmax()` so columns
collapse/wrap responsively, or move to a smaller number of columns at
narrower breakpoints via a media query or container query. For wide
children like tables or images, add `overflow-x: auto` or `max-width:
100%` scoped to that child so the overflow is contained and scrollable
rather than blowing out the grid.

## Pitfalls
- Applying `overflow: hidden` on the grid item without also fixing
  `min-width: auto` just clips content silently instead of fixing the
  sizing, which can hide important text with no visual indication
  anything was cut off.
- Switching every track to `auto-fit`/`minmax(0, 1fr)` indiscriminately
  can cause columns to collapse to zero width when the container gets
  very narrow, producing invisible content instead of a graceful
  reflow -- keep a sane minimum in the `minmax()` for tracks holding
  meaningful content.

## Verify
Open the DevTools grid overlay, shrink the viewport or container to the
narrowest supported width, and confirm the item's rendered box stays
within its track boundary (no red overflow indicator/no content crossing
into the neighboring column) while the previously-overflowing content now
wraps, truncates, or scrolls internally.
