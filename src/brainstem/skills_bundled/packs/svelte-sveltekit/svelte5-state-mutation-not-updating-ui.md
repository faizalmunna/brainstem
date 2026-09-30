---
name: svelte5-state-mutation-not-updating-ui
description: Diagnose a Svelte 5 component where mutating a nested property on a $state object or array silently fails to update the rendered UI.
triggers: ["$state not reactive", "mutating state doesn't update ui", "nested object not updating svelte", "svelte 5 array push not reactive", "state.raw not updating"]
permissions: ["READ"]
---

## Symptom
A component declares `let obj = $state({ ... })` (or an array), the code
mutates a nested field or calls `.push()`/`.splice()` on it directly, and
the template that reads that value doesn't re-render -- even though the
same pattern "just works" for top-level primitives declared with
`$state()`.

## Likely causes
1. **The state was created with `$state.raw()` instead of `$state()`.**
   `$state.raw` intentionally opts out of deep reactivity -- it only
   notifies on full reassignment of the variable itself, not on mutation
   of its contents. Code copied from an older example or "optimized" for
   perf by switching to `.raw` loses nested mutation tracking.
2. **A primitive was destructured out of the reactive object** (`let
   { count } = state`) and the code mutates the local `count` variable
   afterward. Destructuring copies the primitive by value at that instant;
   the local binding is no longer connected to the proxy, so reassigning
   it never touches `state.count`.
3. **The object was cloned via spread or `structuredClone`** (`let copy =
   {...state}` or `$state.snapshot(state)`) before being mutated. Both
   produce a plain, non-proxied object disconnected from the original
   reactive source -- mutating `copy` never touches `state`.
4. **The value is a class instance, `Map`, or `Set` that Svelte's deep
   proxy doesn't instrument the way plain objects/arrays are** -- native
   `Map`/`Set` mutations (`.set()`, `.add()`, `.delete()`) on a plain
   `new Map()` wrapped in `$state()` aren't tracked per-entry unless you
   use the reactive versions from `svelte/reactivity` (`SvelteMap`,
   `SvelteSet`).
5. **The mutated object never actually came from `$state`** -- it was
   passed in as a prop from a parent that itself holds a plain
   (non-reactive) object, or read once in `onMount` and stored in a
   non-reactive module-level variable.

## Diagnose
- Check the declaration site: is it `$state(...)` or `$state.raw(...)`?
  Search the file for `.raw(` -- that's the fastest way to rule in/out
  cause 1.
- Add a one-line `$inspect(obj)` (Svelte 5's built-in reactive logger)
  right above the template usage; it logs every time Svelte detects a
  change to tracked state. If a mutation doesn't produce a log line, the
  proxy isn't seeing the write at all.
- For destructuring, grep for `let { ... } = state` followed later by a
  bare reassignment of one of those names -- that reassignment is
  touching a local variable, not the proxy.
- Log `Object.getPrototypeOf(obj)` or check `obj === $state.snapshot(obj)`
  -- if they're equal (or the object behaves like a plain object with no
  reactivity), it was never a live proxy to begin with.
- For Map/Set, confirm the import: `import { SvelteMap } from
  'svelte/reactivity'` vs. a bare `new Map()`.

## Fix
- If deep reactivity is actually wanted, switch `$state.raw()` back to
  `$state()` -- `.raw` should only be used for large objects you always
  replace wholesale (e.g. data fetched fresh each time) as a deliberate
  performance opt-out, not as a default.
- Never destructure a primitive out of reactive state if you intend to
  mutate it afterward -- keep referencing `state.count` directly, or
  destructure only to *read* a snapshot value that's allowed to go stale.
- Don't spread/clone a `$state` object mid-flow unless you intend to
  create an independent, disconnected copy on purpose (e.g. an "undo"
  snapshot) -- mutate the original reference in place, or reassign the
  whole property (`state.list = [...state.list, next]`) if you do want a
  fresh array while keeping the *outer* `state` object reactive.
- For `Map`/`Set`, import `SvelteMap`/`SvelteSet` from
  `svelte/reactivity` so individual `.set()`/`.add()`/`.delete()` calls
  are tracked per-entry, matching how the deep proxy handles plain
  objects and arrays.
- If the object legitimately originates outside the component (a prop,
  an imported module value), make sure it was declared with `$state` at
  its *source*, not wrapped locally -- wrapping a plain object passed in
  as a prop with local `$state()` creates a second, disconnected copy.

## Pitfalls
- Overcorrecting by wrapping everything in `$state()`, including large,
  rarely-mutated data structures, defeats the point of `$state.raw` and
  can hurt performance on genuinely big datasets -- use `.raw` where a
  wholesale-replace pattern is the actual usage, not as a blanket ban.
- "Fixing" a destructuring bug by wrapping the destructured primitive in
  its own `$state()` (`let count = $state(state.count)`) creates a second
  independent reactive value that starts in sync but immediately diverges
  from the source on the next external update -- the real fix is to stop
  destructuring, not to re-wrap the copy.

## Verify
Add a temporary `$inspect(obj)` call and perform the mutation that was
failing; confirm a new log entry appears with the updated value, then
confirm the DOM node bound to that value updates in the browser without a
full re-render of the component. Remove the `$inspect` call afterward.
