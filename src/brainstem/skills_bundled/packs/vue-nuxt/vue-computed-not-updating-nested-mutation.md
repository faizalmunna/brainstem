---
name: vue-computed-not-updating-nested-mutation
description: Fix a computed property that fails to recompute when a deeply nested property of its source object changes.
triggers: ["computed not updating nested object", "computed property stale", "computed doesn't react to deep change", "shallowReactive not updating computed", "vue computed cache not invalidating"]
permissions: ["READ"]
---

## Symptom
A `computed` re-evaluates fine when a top-level property or the whole
object is reassigned, but silently keeps returning a stale value when a
property two or three levels deep inside the same source object is
mutated, and the template doesn't update either.

## Likely causes
1. **The source is a plain JS object, never wrapped in `reactive()` or
   `ref()`**, so mutating a nested field never notifies Vue's reactivity
   system at all -- there was nothing to track in the first place.
2. **The computed getter never actually reads the specific nested path**
   that changed -- e.g. it reads `obj.list` (the array reference) but the
   mutation only changes `obj.list[2].value`, and if the getter doesn't
   iterate/access that property, Vue's dependency tracker has no reason
   to know about it.
3. **`shallowRef`/`shallowReactive` is used** (intentionally, often for
   performance on a large object) which only tracks the top-level
   reference/properties, not nested mutations -- this is working as
   designed, not a bug, but easy to forget was applied several files away.
4. **The nested object came from a non-reactive transformation** -- e.g.
   fetched data assigned into a reactive array via `.map()` that returns
   new plain objects, where only the outer array is reactive and each
   element itself isn't deeply proxied the way `reactive()` on the whole
   structure would have made it.

## Diagnose
- Add `console.log` inside the computed getter to confirm whether it's
  even being invoked again after the mutation -- if it's not invoked at
  all, the dependency was never tracked; if it's invoked but returns the
  same value, the bug is elsewhere (e.g. a stale closure).
- Inspect the source object in Vue devtools: a `reactive()`-wrapped object
  shows as a Proxy; a plain object does not. This immediately confirms or
  rules out cause 1.
- Grep the file (and the composable that produced the source, if
  different) for `shallowRef`/`shallowReactive` to rule out cause 3.

## Fix
Ensure the source is genuinely deep-reactive: use `reactive()` for
objects that need nested tracking (or plain `ref()`, which deep-unwraps
nested objects by default), and make sure the computed getter actually
reads the property that should trigger it -- often naturally satisfied by
iterating (`obj.list.map(i => i.value)`) rather than only touching the
outer reference. If `shallowRef`/`shallowReactive` was a deliberate
performance choice, keep it and instead call `triggerRef()` after
mutating nested data, or replace the top-level reference
(`state.value = { ...state.value }`) to explicitly signal the change
rather than relying on deep tracking that was intentionally turned off.

## Pitfalls
Swapping every `shallowRef`/`shallowReactive` in the codebase for a deep
`reactive()`/`ref()` to make this one computed work again can quietly
reintroduce the performance problem the shallow variant was solving
(e.g. deeply proxying a large list on every render) -- scope the fix to
the one object that actually needs deep tracking.

## Verify
Mutate the specific nested property directly (via devtools console or a
test action) and confirm both that the computed getter's log fires again
with the updated value and that the rendered DOM reflects it, without
needing a full remount or page reload.
