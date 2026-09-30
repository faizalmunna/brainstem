---
name: z-index-trapped-in-stacking-context
description: Diagnose a very high z-index that is still ignored because an ancestor element creates its own stacking context.
triggers: ["z-index 9999 not working", "z-index isn't doing anything", "element stuck behind another element", "high z-index still hidden", "dropdown appears behind modal"]
permissions: ["READ"]
---

## Symptom
An element has `z-index: 9999` (or higher than everything else on the
page) but still renders behind another element that has a much lower or
no explicit `z-index` -- raising the value further has no effect at all.

## Likely causes
1. **An ancestor of the element creates a new stacking context** (via
   `transform`, `opacity < 1`, `filter`, `will-change`, `perspective`,
   `mix-blend-mode`, `isolation: isolate`, or `position` + `z-index`
   together), so the element's `z-index` is only compared against its
   siblings *inside that context* -- it can never climb above content
   that lives in a sibling stacking context painted later, no matter how
   high the number is.
2. **The element competing for top position is inside a later-painted
   stacking context of its own** (e.g. a modal portal appended near the
   end of `<body>`), so it wins purely by paint order regardless of
   z-index values on either side.
3. **`z-index` is set on an element with `position: static`**, where it
   is simply ignored by the spec -- the property only has effect on
   positioned (`relative`/`absolute`/`fixed`/`sticky`) or flex/grid-item
   elements.
4. **A `contain: layout` or `contain: paint` on an ancestor** also
   creates a new stacking context, which is easy to miss because it
   doesn't look like a "visual" property the way `opacity` or `transform`
   does.

## Diagnose
- In Chrome/Edge DevTools, select the element, open the "Layout" pane,
  and check the "Rendering" tab's paint order, or use the dedicated
  "z-index stacking contexts" view in Firefox DevTools (inspector shows
  a small context badge on elements that create one).
- Walk up the ancestor chain in the Elements panel checking computed
  styles for `transform`, `opacity`, `filter`, `will-change`, `isolation`,
  and `contain` on every parent -- any one of these creates a boundary
  the child's z-index cannot cross.
- Temporarily remove the suspected property (e.g. comment out
  `transform: translateZ(0)` on the parent) in DevTools and see if the
  element immediately jumps to the correct layer -- confirms which
  ancestor is the trap.

## Fix
Move the stacking-context-creating property off the ancestor if it isn't
load-bearing (e.g. a `transform` left over from an old animation), or --
if it must stay -- raise the *ancestor's* stacking context instead of the
child's z-index, since stacking order is decided between sibling contexts,
not by digging inside them. When the two competing elements are portalled
(one lives outside the DOM subtree of the other, e.g. a modal appended to
`document.body`), the fix is architectural: render the element that needs
to be on top from the same top-level stacking layer as its competitor
(same portal root, or promote both to `position: fixed` at the body level)
rather than chasing z-index numbers across unrelated subtrees.

## Pitfalls
- "Fixing" this by setting `z-index: 999999` on increasingly higher
  ancestors just relocates the trap one level up and often breaks
  stacking for unrelated siblings of those ancestors.
- Removing a `transform`/`will-change` to escape a stacking context can
  silently kill a GPU-accelerated animation or a `backdrop-filter` effect
  that depended on it -- check what the property was doing before deleting
  it, not just that removing it "fixed" the z-index issue.

## Verify
With the ancestor chain's stacking contexts identified and the fix
applied, confirm in DevTools that the target element's computed stacking
context is now a sibling (not a descendant) of the context it needs to
appear above, and visually confirm it renders on top across the specific
interaction that triggered the bug (open dropdown, hover tooltip, etc.).
