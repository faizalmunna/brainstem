---
name: text-ellipsis-not-working-in-flex-child
description: Fix text-overflow ellipsis truncation that does nothing on a flex or grid child even though all three ellipsis properties are set.
triggers: ["text-overflow ellipsis not working", "truncation not working in flexbox", "ellipsis not showing in flex item", "text overflowing instead of truncating", "white-space nowrap not truncating"]
permissions: ["READ"]
---

## Symptom
An element has the standard truncation trio --
`white-space: nowrap; overflow: hidden; text-overflow: ellipsis;` -- but
instead of truncating with "...", the text either overflows its box
visibly or wraps onto multiple lines, most often when the truncated
element is a direct child of a flex or grid container.

## Likely causes
1. **The flex/grid item's default `min-width: auto`** (the same root
   cause as the general flex-shrink skill) means the item never actually
   shrinks smaller than its text's full width, so `overflow: hidden` never
   has any overflow to hide -- the box just keeps growing to fit the text
   instead.
2. **The element with the ellipsis properties has no defined or
   constrained width at all** -- `text-overflow: ellipsis` only does
   anything once the box has a narrower width than its content, whether
   that width comes from a fixed value, a `%`, or a flex-shrink result.
3. **The ellipsis properties are set on the wrong element** -- e.g. on a
   wrapper `div` while the actual text lives in a nested `span` that has
   its own sizing, or on a flex/grid container instead of the text-bearing
   child itself.
4. **`display` on the truncated element is `flex`, `grid`, or `inline`**
   instead of `block`/`inline-block` -- `text-overflow` only applies to
   block containers with overflow, so an element that is itself a flex
   container showing text as a child (rather than as its own inline
   content) won't truncate at that level.

## Diagnose
- In DevTools, select the text element and check computed `width` -- if
  it matches the text's natural rendered width almost exactly, there is
  no constrained width for the ellipsis to activate against.
- Check `min-width` on the same element and its flex/grid item ancestor
  chain for the `auto` default described above.
- Confirm in the Elements panel that `overflow`, `white-space`, and
  `text-overflow` are all computed on the *same* element that directly
  contains the text node, not a wrapper around it.

## Fix
Set `min-width: 0` on the flex/grid item in the ancestor chain (exactly
as with the general shrink-to-content fix), and give the truncating
element itself a definite width constraint -- either an explicit
`width`/`max-width`, or let it inherit a shrunk width from `flex: 1
1 0%` combined with the `min-width: 0` fix, so the browser has a box
narrower than the text to truncate against. Apply the three-property
ellipsis trio directly on the element wrapping the text node, and ensure
that element's `display` is `block` or `inline-block` rather than a flex
or grid container itself (nest an inner `span`/`div` for the text if the
outer element must stay a flex container for other children like an
icon).

## Pitfalls
- Adding `overflow: hidden` alone without addressing `min-width: auto`
  is the most common half-fix -- it looks like it should work by the
  property list alone, but produces no visible change since the box never
  shrinks below the text's width in the first place.
- Setting a hardcoded `width` in pixels to force truncation can look
  fixed in isolation but breaks responsively -- prefer `min-width: 0`
  plus a flexible `width`/`flex-basis` so truncation kicks in
  proportionally to available space rather than at one fixed breakpoint.

## Verify
Shrink the container (resize the browser or its parent) until the text's
natural width exceeds the available space, and confirm the text now
visibly truncates with an ellipsis rather than overflowing or wrapping,
at the specific narrow width where the bug was originally reported.
