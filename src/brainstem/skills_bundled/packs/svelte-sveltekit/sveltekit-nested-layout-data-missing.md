---
name: sveltekit-nested-layout-data-missing
description: Diagnose a deeply nested SvelteKit page whose data prop is missing a field that a parent layout's load function clearly returned.
triggers: ["layout data not available in page", "data undefined nested route sveltekit", "parent load data missing", "await parent not working sveltekit", "sveltekit data merge collision"]
permissions: ["READ"]
---

## Symptom
A `+layout.server.js` (or `+layout.js`) several levels up the route tree
returns a field (e.g. `user`), but a `+page.svelte` several segments
deeper either gets `undefined` for that field, or gets a value that looks
nothing like what the ancestor returned.

## Likely causes
1. **A `load` function needs the ancestor's data as an input and forgets
   `await parent()`.** Unlike the automatic merge that supplies the
   `data` prop to components, a `load` function's *own logic* only sees
   ancestor data if it explicitly awaits `parent()` -- skipping this
   means the function computes its result without that field, which then
   silently propagates as missing to everything below it.
2. **A shallow key collision between load functions at different
   levels.** SvelteKit merges the return values of every `load` function
   in the route hierarchy into one `data` object; if two levels return a
   property with the same name (`user` at the root layout and a
   differently-shaped `user` at a page three levels down), the deeper
   one silently wins for that key -- the "missing" ancestor field is
   actually just shadowed, not absent.
3. **An intermediate `+layout.js` (universal load) receives merged `data`
   as its first argument but returns a new object without spreading
   it** (`return { extra }` instead of `return { ...data, extra }`) --
   this drops everything computed by ancestors and its own sibling
   `+layout.server.js` for that level, breaking propagation to every
   route below it.
4. **The field is only conditionally returned** (e.g. inside `if
   (locals.user) { return { user } }` with no `else` branch returning
   `user: null`), so it's `undefined` on some requests in a way that
   looks like a wiring bug but is actually a real, unhandled falsy case
   in the deeper page's logic.

## Diagnose
- Log the return value of every `load` function in the chain from root to
  the failing page (`+layout.server.js`, `+layout.js`, `+page.server.js`,
  `+page.js`) to see exactly which level first fails to include the
  expected field.
- Grep every `load` function in the chain for `parent(` -- confirm any
  level that needs ancestor data to compute its own result actually
  awaits it, rather than assuming it's automatically available inside the
  function body (it's only automatic in the component's `data` prop, not
  inside another `load` function).
- Search all `load` functions in the hierarchy for a repeated top-level
  key name (e.g. `user`, `data`, `settings`) -- a collision is easy to
  miss when the levels are in different files.
- Check any `+layout.js` that accepts `data` as a parameter and confirm
  its return statement spreads `...data` rather than replacing it
  entirely.

## Fix
- Add `await parent()` inside any `load` function whose own computation
  depends on an ancestor's returned data, and merge it explicitly
  (`return { ...parentData, ...ownFields }`) if it also needs to pass
  that data through further down.
- Rename colliding keys so each level contributes a uniquely-named field,
  or intentionally merge them inside a `load` function that awaits
  `parent()` and combines both under one clear shape before returning.
- Make sure every `+layout.js` that receives `data` and returns something
  new spreads the incoming `data` first, adding only the new fields on
  top, so nothing computed by an ancestor or a sibling server load is
  dropped.
- Always return a defined value (even `null`) for conditionally-available
  fields, and have the deepest consumer treat `null` as an explicit,
  handled state rather than relying on `undefined` falling through
  silently.

## Pitfalls
- Reflexively adding `await parent()` to every `load` function "just in
  case" creates unnecessary coupling and can reintroduce the
  load-reruns-unexpectedly problem, since a load awaiting `parent()`
  reruns whenever the parent reruns -- add it only where the data is
  actually needed as an input.
- Fixing a key collision by renaming only in the deepest page (leaving
  the ancestor's field name unchanged and just reading a different key
  locally) treats the symptom, not the cause, and the same collision will
  resurface for the next contributor who doesn't know about the
  workaround -- rename at the source or merge deliberately.

## Verify
Log (or inspect via devtools) the fully merged `data` object received by
the deepest page component and confirm the expected field is present with
the correct value from the ancestor load, then change the ancestor's
value and confirm it propagates through to the deep page on the next
navigation without needing to touch the intermediate levels.
