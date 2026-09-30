---
name: vue-ref-reactive-unwrapping-confusion
description: Fix a ref that renders as an object or requires inconsistent .value access across template and script in Vue 3.
triggers: ["ref shows object object in template", "do i need .value here", "ref not unwrapping in template", "nested ref not unwrapping", "ref inside reactive confusing"]
permissions: ["READ"]
---

## Symptom
A value alternates between needing `.value` and not needing it depending
on where it's accessed: a `{{ count }}` interpolation shows the number
fine, but `{{ state.list[0].counter }}` shows `[object Object]`, or code
that worked when a ref was top-level breaks once it's moved inside a
plain array or object.

## Likely causes
1. **Template auto-unwrapping only applies to top-level bindings** returned
   from `setup()`/`<script setup>` and to top-level properties of a
   `reactive()` object -- a `ref` nested inside a plain (non-reactive)
   array or a `Map` is not auto-unwrapped, so you still need `.value` or
   `unref()` to read it.
2. **Storing a `ref` as a property of a `reactive()` object** auto-unwraps
   when *read or written* through the reactive object in script
   (`state.someRef` acts like the plain value, and `state.someRef = x`
   works too) -- but if that same ref is later destructured out
   (`const { someRef } = state`), the unwrapping behavior disappears and
   you're back to a plain value or a raw `Ref`, confusing anyone who
   copies code from one context to the other.
3. **Mixing `ref()` and `reactive()` for the same kind of data** across a
   codebase without a convention, so some composables return refs and
   others return reactive objects, and callers guess wrong about whether
   `.value` is needed.
4. **A ref returned from a computed or composable is stored inside a plain
   JS array built with `.map()`**, which does not get the reactive
   auto-unwrap treatment that a `reactive()`-wrapped array would.

## Diagnose
- `console.log` the exact value right before use: if it prints something
  like `RefImpl {value: ...}` instead of the raw value, it needs
  `unref()`/`.value` at that access point.
- Check whether the containing structure is the result of `reactive(...)`
  (auto-unwraps top-level ref properties) versus a plain object/array
  literal or `.map()` result (does not).
- In the template, if interpolation shows `[object Object]`, that specific
  binding is an un-unwrapped ref or reactive object being coerced to a
  string, not a rendering bug elsewhere.

## Fix
Adopt one consistent rule per boundary: inside `<script setup>`, always
use `.value` explicitly when reading/writing a ref you hold a direct
reference to (don't rely on auto-unwrap tricks in script). In templates,
rely on auto-unwrap only for top-level `setup()` return values and direct
properties of a `reactive()` object; for anything nested in a plain
array/object, unwrap explicitly with `unref(item)` in a computed before
it reaches the template, or restructure the data so template access paths
stay shallow. When designing a composable's return value, pick either
"returns refs" or "returns a reactive object" and document it, rather
than mixing per-property.

## Pitfalls
Adding `.value` in a template out of habit or trial-and-error ("it works
now") often breaks later when someone changes the underlying source from
a plain value to a real top-level ref -- because template auto-unwrap
means the correct template code should *not* have `.value` there, and now
it errors with `Cannot read properties of undefined (reading 'value')` or
silently unwraps twice.

## Verify
Log `typeof` and `isRef(...)` for the value at both the point it's
produced and the point it's consumed, confirm they agree on whether it's
a ref or a plain value, and confirm the template renders the actual data
(not `[object Object]`) after the fix.
