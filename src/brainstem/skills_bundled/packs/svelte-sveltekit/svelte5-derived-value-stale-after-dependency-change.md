---
name: svelte5-derived-value-stale-after-dependency-change
description: Diagnose a Svelte 5 $derived value that fails to update after one of its underlying dependencies changes inside a nested function call.
triggers: ["$derived not updating", "derived value stale svelte", "derived.by not recomputing", "computed value stuck svelte 5", "svelte derived stale closure"]
permissions: ["READ"]
---

## Symptom
A `$derived(...)` or `$derived.by(() => ...)` value stops updating after a
change to something it should depend on -- often only when the
computation calls out to a helper function, does async work, or reads the
dependency indirectly rather than as a direct top-level expression.

## Likely causes
1. **An `await` inside `$derived.by(() => { ... })`.** Svelte only tracks
   reactive reads made *synchronously* during the derivation's initial
   execution. Any state read after the first `await` happens outside that
   tracking window and is invisible to the dependency graph -- the derived
   value simply never reruns when that later-read value changes.
2. **A helper function destructures a primitive out of `$state` before
   the derived call happens**, then the derived expression calls that
   helper with the already-destructured (plain, disconnected) value
   instead of the live reactive reference -- the derivation depends on a
   stale copy, not the source.
3. **Reference-equality memoization outside Svelte's reactivity** (a
   manually memoized helper, a UI library prop diff, or `Object.is`-style
   caching) treats a mutated `$state` array/object as unchanged, because
   Svelte's deep proxy mutates objects *in place* -- the reference never
   changes even though the contents did, so anything checking identity
   rather than reading through the proxy sees "no change."
4. **The read happens inside `untrack()`** (used elsewhere to intentionally
   break a reactive loop) that was copy-pasted into this derivation,
   silently exempting a needed dependency from tracking.

## Diagnose
- Search the `$derived.by` body for `await` -- any reactive state read
  after that point is untracked by construction, not a bug in Svelte.
- Add `$inspect(dependency)` next to the derived declaration to confirm
  the source value is actually changing; if it is, but the derived output
  isn't, the break is in how the derived reads it, not in the source.
- Check whether the derived calls a helper function and whether that
  helper receives a primitive (already read) versus the reactive object
  itself -- passing `state.value` (a copy at call time) versus `state`
  (a live reference the callee reads from) behaves very differently.
- Grep the derivation and anything it calls for `untrack(` -- confirm it
  isn't wrapping a read that should stay tracked.
- If a memoization/caching layer is involved (e.g. a library prop
  comparison), log the object's reference (`console.log(obj === prevObj)`)
  before and after the mutation to confirm it's unchanged, which points at
  cause 3 rather than a Svelte bug.

## Fix
- Move any `await` out of the tracked portion of `$derived.by`: read every
  reactive dependency synchronously first (into local variables) at the
  top of the function, then do async work afterward if needed -- or, if
  the computation is inherently async, use `$effect` to write the result
  into a separate `$state` variable instead of trying to make `$derived`
  itself asynchronous.
- Pass the reactive source (the object/array itself, or a getter) into
  helper functions rather than an already-extracted primitive, so the
  read that establishes the dependency happens inside the derivation's
  synchronous execution, not before it.
- For reference-equality consumers, either read through
  `$state.snapshot()` to get a plain, comparably-fresh snapshot each time,
  or restructure so the consumer re-derives from primitive fields
  (`obj.updatedAt`, `obj.length`) rather than comparing the container's
  identity.
- Remove stray `untrack()` calls around reads that should participate in
  the dependency graph; keep `untrack` scoped only to the specific read
  that was causing an intentional infinite-loop break elsewhere.

## Pitfalls
- Wrapping the entire `$derived.by` body in `untrack(() => ...)` to "stop
  the warnings" during debugging and forgetting to remove it turns the
  derived into a value that only computes once and never updates again --
  a much worse bug than the one being chased.
- Splitting every derived into `$state` + `$effect` pairs as a reflexive
  workaround for staleness reintroduces the exact ordering/timing bugs
  runes were meant to avoid, and usually isn't necessary once the actual
  untracked read is found -- reserve that pattern for genuinely async
  derivations.

## Verify
Trigger the dependency change that previously didn't propagate, and
confirm both an `$inspect` log for the derived value fires with the new
result and the rendered UI reflects it immediately, with no extra
navigation or remount required.
