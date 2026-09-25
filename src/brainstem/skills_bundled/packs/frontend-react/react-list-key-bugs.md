---
name: react-list-key-bugs
description: Diagnose list-rendering bugs caused by missing, index-based, or unstable React keys (wrong item highlighted, form state bleeding between rows, animation glitches).
triggers: ["wrong item selected", "list item state bleeds", "key prop warning", "each child in a list should have a unique key", "list reorders wrong", "form values swap rows"]
permissions: ["READ"]
---

## Symptom
Reordering, inserting, or deleting an item in a rendered list causes the
*wrong* row to show a highlight/selection/edit state, an input's typed
text appears to jump to a different row, or an animation/transition plays
on the wrong element -- often with no React warning at all if a key is
present but wrong (index-based).

## Likely causes
1. **Using the array index as the key** (`items.map((item, i) => <Row
   key={i} .../>)`) on a list that can reorder, filter, or have items
   inserted/removed anywhere but the end -- React matches elements by key
   across renders, so index keys cause it to reuse the wrong DOM node and
   its component state for a different logical item.
2. **No key at all**, which React warns about and effectively falls back
   to positional matching -- same failure mode as index keys, just with a
   console warning attached.
3. **A key that isn't actually stable/unique**, e.g. derived from
   something that changes on edit (using the item's display name as the
   key when the name itself is editable).
4. **Duplicate keys** from data that isn't actually unique (two items
   sharing an ID because of a backend bug or a client-side merge), which
   causes React to silently drop or misattribute one of them.

## Diagnose
- Check the `.map()` call generating the list: is the key `index`, or
  derived from a field that can change or collide?
- Reproduce by inserting an item at the *start* or *middle* of the list
  (not the end) and checking whether per-row local state (an open/closed
  toggle, an input's typed value, a checked checkbox) stays attached to
  the correct row or shifts.
- For "duplicate key" warnings, log the array of keys right before
  rendering and check for actual duplicates in the data.

## Fix
- Key on a stable, unique identifier from the data itself (a database ID,
  a UUID) -- never the array index, unless the list is provably static
  (never reordered, filtered, or spliced) for its entire lifetime.
- If the data genuinely has no stable ID yet (e.g. newly created,
  unsaved items), generate one client-side at creation time (a UUID or
  incrementing counter kept in state) and keep using that same generated
  ID through re-renders, rather than re-deriving it from mutable fields.
- For duplicate-key data bugs, fix the dedup logic upstream (in the query
  or the merge step) rather than patching around it with a composite key
  that happens to be unique today.

## Pitfalls
- "Just add `key={item.id ?? index}`" reintroduces the index-key bug for
  any item that doesn't yet have an ID, silently, which is exactly the
  newly-created-item case where this bug is most visible to users.
- Switching to a stable key can *expose* pre-existing per-row state bugs
  that index keys were accidentally masking (because the wrong-but-
  consistent remounting hid a missing reset-on-id-change effect) --
  treat a fix here as something to test the surrounding component with,
  not just the key line itself.

## Verify
With a stable key in place, insert a new item at the top of the list and
confirm every existing row's local state (toggles, inputs, selection)
stays attached to the same logical item, not the same list position.
