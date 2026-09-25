---
name: angular-ngfor-trackby-missing-dom-churn
description: Diagnose an ngFor list that fully recreates every DOM node on each update instead of patching only the item that changed.
triggers: ["ngfor recreating dom nodes", "list loses focus on update angular", "trackby missing angular performance", "ngfor rerenders entire list angular"]
permissions: ["READ"]
---

## Symptom
A list rendered with `*ngFor` recreates every DOM node on each data
update -- visible as the whole list flashing in DevTools' Elements panel,
a focused input inside a row losing focus, scroll position resetting, or
a CSS transition restarting -- even when only one item in the underlying
array actually changed.

## Likely causes
1. **No `trackBy` function is provided to `*ngFor`**, so Angular's
   default tracking uses each array element's object identity -- when the
   array is replaced wholesale (a fresh HTTP response, or an immutable
   update that reconstructs every item), every element looks "new" and
   gets destroyed and recreated even if its data is unchanged.
2. **A `trackBy` function is provided but returns the array index**
   (`(index, item) => index`), which defeats the purpose whenever items
   are inserted, removed, or reordered -- every item after the change
   point gets treated as a different item at that position.
3. **The `trackBy` function keys off a field that changes on every
   update** (e.g. a `lastUpdated` timestamp) instead of a stable unique
   id, making it functionally equivalent to having no `trackBy` at all.
4. **Row components inside the `*ngFor` aren't `OnPush`**, so even with a
   correct `trackBy` preventing node recreation, each row still runs a
   full change-detection check on every parent update -- a related but
   distinct performance issue from DOM-node churn.

## Diagnose
- In Chrome DevTools' Elements panel, watch the default node-mutation
  highlight while triggering a list update -- highlighting across the
  *entire* list rather than just the one changed row confirms full node
  recreation, not just a re-render.
- Check whether an input inside a row loses focus, or a CSS
  transition/animation on an unrelated row restarts, immediately after a
  data refresh that should have touched only one item -- both are
  reliable signs of node recreation.
- Grep the `*ngFor` directive for a `trackBy:` binding; if present, read
  the function to confirm it returns a stable, unique field (e.g.
  `item.id`) rather than the loop index or a field that mutates on every
  update.

## Fix
- Add a `trackBy` function returning each item's stable unique identifier
  (a database id or UUID) so Angular can match old and new array elements
  by identity across updates, patching only the rows whose item actually
  changed and reusing/reordering the rest.
- If items genuinely lack a natural unique id, generate and attach a
  stable one at the point data first enters the app (fetch or creation
  time) rather than relying on array position, so `trackBy` has something
  reliable to key off of.
- Combine `trackBy` with `ChangeDetectionStrategy.OnPush` on the row
  component so that, beyond DOM nodes being preserved, the row's own
  change-detection work is also skipped unless its specific `@Input`
  reference changed.

## Pitfalls
- Adding `trackBy: (i) => i` just to silence a lint warning about a
  missing `trackBy` provides no real benefit over the default and can
  make reordering bugs *worse* in some cases by matching the wrong item
  to the wrong index.
- Introducing `trackBy` on a list where rows are intentionally meant to
  fully reset on certain updates (e.g. a "clear all filters" action that
  should also collapse each row's expanded/collapsed local UI state)
  removes that reset as a side effect -- confirm the row's local state is
  actually meant to persist across the specific updates in question.

## Verify
Trigger an update that changes only one item in the list (not the whole
array wholesale) and confirm in the Elements panel that only that item's
DOM node is recreated or updated, while other rows' nodes, any focused
input, and any in-progress CSS transition on unrelated rows remain
undisturbed.
