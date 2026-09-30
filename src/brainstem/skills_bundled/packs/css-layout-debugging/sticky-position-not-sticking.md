---
name: sticky-position-not-sticking
description: Diagnose a position sticky element that scrolls away normally instead of sticking, usually due to an ancestor's overflow or sizing.
triggers: ["position sticky not working", "sticky header not sticking", "sticky element scrolls away", "sticky sidebar not sticky", "sticky nav stops working"]
permissions: ["READ"]
---

## Symptom
An element with `position: sticky` and a `top`/`bottom` offset behaves
exactly like `position: static` -- it scrolls out of view with the rest
of the page instead of pinning to the viewport edge once it reaches its
threshold, with no console error or warning to explain why.

## Likely causes
1. **An ancestor between the sticky element and the scroll container has
   `overflow` set to anything other than `visible`** (`hidden`, `auto`,
   `scroll`), even if that ancestor isn't the one actually scrolling --
   per spec, sticky positioning is computed relative to the nearest
   scrolling ancestor, and a non-`visible` overflow on any ancestor in
   between disqualifies the sticky behavior for that axis.
2. **The sticky element or a direct ancestor doesn't have enough height**
   to ever leave the viewport in the first place -- if the ancestor's
   content is shorter than the viewport, or exactly the sticky element's
   own height, there is no scroll range for the sticking behavior to be
   visible during.
3. **No `top` (or `bottom`/`left`/`right`) offset is set at all** -- sticky
   with no threshold value has undefined/no visible sticking point in
   most browsers, since the browser doesn't know when to start pinning.
4. **A `transform`, `filter`, or `will-change` on an ancestor**, which --
   the same as with stacking contexts -- also changes what counts as the
   containing block for the sticky element, causing it to stick relative
   to the wrong ancestor's box (often making it look like it "isn't
   sticking" when it's actually sticking relative to a small nearby box
   that itself scrolls out of view immediately).
5. **The element or an ancestor has `display: flex`/`grid` with default
   `align-items: stretch`/height behavior swallowing the intended
   height**, subtly related to cause 2 but worth checking separately
   since flex/grid sizing defaults are less obvious than explicit CSS.

## Diagnose
- In Chrome DevTools, select the sticky element -- the Styles pane shows
  a small warning icon/note next to `position: sticky` when it detects an
  overflow ancestor that breaks it, directly naming the problem.
- Walk up the ancestor chain checking computed `overflow-x`/`overflow-y`
  on each one (including `overflow: auto` added for an unrelated
  scrollable region) up to the actual scrolling container.
- Check the ancestor chain for `transform`/`filter`/`will-change` as well,
  since these change the sticky element's containing block the same way
  they change stacking context.
- Confirm a `top` (or relevant offset) value is actually set in computed
  styles, not left as `auto`.

## Fix
Remove or relocate the `overflow` property from whichever ancestor is
breaking the sticky chain, if it isn't functionally required there; if it
is required (e.g. a genuinely scrollable panel), move the sticky element
so it is a direct descendant of that scrolling container rather than
nested inside another `overflow`-bearing wrapper in between. Ensure the
sticky element's immediate parent has enough height/content to produce
real scroll distance, since sticky has nothing to demonstrate against
inside a short container. Set an explicit offset (commonly `top: 0`) so
the browser has a defined threshold to stick at.

## Pitfalls
- Removing `overflow: hidden`/`auto` from an ancestor to fix stickiness
  can unhide unwanted scrollbars or unclipped content that ancestor was
  relying on that property for -- check what else depends on it before
  deleting it.
- Wrapping the sticky element in an extra `div` to "get it out of" the
  overflow ancestor without actually moving it out of that ancestor's
  DOM subtree does nothing, since the disqualifying overflow ancestor is
  still in the chain either way -- the element has to leave that
  ancestor's subtree, not just gain a new immediate parent.

## Verify
Scroll the page (or the relevant scroll container) past the sticky
element's natural position and confirm it pins to the specified offset
and stays visible while the rest of its sibling content continues
scrolling underneath/past it, at the specific breakpoint or scroll
container where the bug was originally reported.
