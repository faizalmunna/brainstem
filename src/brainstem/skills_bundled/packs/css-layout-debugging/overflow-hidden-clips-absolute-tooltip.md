---
name: overflow-hidden-clips-absolute-tooltip
description: Fix a dropdown, tooltip, or popover that gets clipped or cut off because an ancestor has overflow hidden or auto set.
triggers: ["tooltip cut off", "dropdown gets clipped", "popover cut off at edge", "overflow hidden hiding dropdown", "select menu clipped by card"]
permissions: ["READ"]
---

## Symptom
A `position: absolute` (or `fixed`) tooltip, dropdown menu, or popover
renders partially or entirely invisible -- cut off in a straight line at
the edge of some containing box -- even though the element's own CSS
positions it correctly and z-index is not the issue (it's not appearing
*behind* anything, it's being visually clipped).

## Likely causes
1. **A positioned ancestor between the tooltip and its offset parent has
   `overflow: hidden` (or `auto`/`scroll`)**, which clips any descendant
   content that extends past its bounds -- this applies even if that
   ancestor's own visible box looks like it has plenty of room, because
   clipping happens at the ancestor's padding-box edge regardless of
   sibling content.
2. **The tooltip's nearest positioned ancestor (the element establishing
   its containing block) is small or has a fixed height**, e.g. a card
   with `position: relative` and `overflow: hidden` used for its own
   rounded-corner clipping, which was never intended to also constrain
   an absolutely-positioned child meant to escape it visually.
3. **A parent uses `overflow: hidden` purely for an unrelated reason**
   (clipping a background image, preventing horizontal scroll from a
   different child) and the tooltip happens to live inside that same
   subtree by coincidence of markup structure, not by design intent.
4. **`overflow: clip` behaving differently from `overflow: hidden`** on
   some ancestor -- both clip, but `clip` additionally disables
   programmatic scrolling, which can mask a related-but-distinct bug if
   someone "fixed" scroll-jumping by swapping to `clip` without realizing
   it still clips visual content the same way.

## Diagnose
- In DevTools, select the tooltip and walk up the "Layout" ancestor
  chain looking for any element with computed `overflow-x`/`overflow-y`
  other than `visible` -- the clipping ancestor is the first one whose
  box the tooltip's rendered rectangle exceeds.
- Temporarily toggle that ancestor's `overflow` to `visible` in the
  DevTools style panel; if the tooltip immediately renders in full,
  that's confirmed as the clipping boundary (remember to revert before
  deciding on a real fix, since removing overflow may break that
  ancestor's own layout).
- Check the tooltip library/component's positioning strategy -- many
  (Popper, Floating UI, native `<dialog>`/`popover` attribute) support
  rendering into a portal specifically to avoid this class of bug, and if
  one is already in use but still clipped, check whether the portal
  target itself is nested inside the clipping ancestor.

## Fix
The structural fix is to render the tooltip/popover in a DOM position
that is not a descendant of the clipping ancestor -- portal it to
`document.body` (or a fixed top-level container) and position it with
coordinates computed from the trigger element's `getBoundingClientRect()`
(a positioning library like Floating UI handles this), so overflow rules
on the original ancestor no longer apply to it at all. When portaling
isn't feasible, the CSS-only compromise is to move the `overflow: hidden`
down to a more specific wrapper that only needs to clip the content that
actually requires it (e.g. clip just an image wrapper for rounded
corners) so the ancestor holding the tooltip's containing block stays
`overflow: visible`.

## Pitfalls
- Removing `overflow: hidden` from the ancestor entirely to unblock the
  tooltip can reintroduce whatever it was clipping for (rounded corners
  bleeding, an internal scrollable list suddenly showing all its content)
  -- isolate the overflow to a narrower wrapper instead of deleting it.
- Portaling fixes the clipping but detaches the tooltip from its trigger
  in the DOM tree, which can silently break CSS that relied on descendant
  selectors or inherited context (theme classes, RTL direction, CSS
  custom properties scoped to the original subtree) -- carry those over
  explicitly (e.g. re-apply the theme class on the portal root).

## Verify
With the fix applied, open the tooltip/dropdown in the scenario that
previously clipped it (near the edge of the scrollable/clipped ancestor)
and confirm it renders fully and is not cut off, then confirm the
ancestor's original clipping behavior (rounded corners, no unwanted
scrollbars) still holds for the content it was actually meant to clip.
