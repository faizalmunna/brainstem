---
name: svelte5-effect-infinite-loop
description: Diagnose a Svelte 5 $effect that runs continuously, freezing the UI or flooding the console because it re-triggers its own dependencies.
triggers: ["$effect infinite loop", "effect_update_depth_exceeded", "svelte 5 effect running forever", "too much recursion svelte effect", "effect keeps firing svelte"]
permissions: ["READ"]
---

## Symptom
The browser tab freezes, the console fills with repeated log lines, or
Svelte throws an `effect_update_depth_exceeded`-style error shortly after
a component mounts or a specific interaction happens -- traced to an
`$effect(...)` block.

## Likely causes
1. **The effect reads and writes the same `$state` variable.** The most
   direct form: `$effect(() => { count = count + 1 })` -- the write
   triggers the effect's own dependency (the read of `count`) to be
   considered dirty, so it reruns immediately, forever.
2. **Two effects update each other's state bidirectionally.** Effect A
   reads state `x` and writes state `y`; effect B reads `y` and writes
   `x`. Neither effect alone looks like a loop, but together they
   ping-pong indefinitely on any single change to either value.
3. **An effect updates a property of an object that a `$derived` (read by
   the same effect) depends on**, so writing triggers the derived to
   recompute, which the effect reads again on its next run, which writes
   again -- an indirect cycle through a derived value rather than a
   direct self-reference.
4. **An effect calls a function with a side effect that mutates state the
   effect also reads**, where the mutation isn't obvious at the call site
   (e.g. a store-like helper, a class method) -- the loop exists but isn't
   visible just from reading the effect's own body.
5. **An effect meant to run only once uses `$effect` instead of
   `$effect.pre` / a one-time guard**, and its setup logic itself causes a
   state change that re-satisfies its own trigger condition every run.

## Diagnose
- Read the exact console error: Svelte's `effect_update_depth_exceeded`
  message names roughly where the loop is; start there rather than
  scanning the whole file.
- For a single effect, list every `$state`/`$derived` value it *reads*
  and every one it *writes* -- any overlap between those two lists is a
  candidate for a direct loop.
- For suspected two-effect ping-pong, temporarily comment out one of the
  two effects and see whether the freeze stops -- if it does, the other
  effect's write is the trigger, not a bug in the commented-out one
  alone.
- Add a `console.trace()` (not just `console.log`) inside the effect
  right before the state write that's suspected to be looping, and check
  the call stack depth/pattern across a few iterations before the tab
  locks up.

## Fix
- If the effect only needs to *compute* a value from other state, replace
  it with `$derived`/`$derived.by` instead -- derived values are meant
  for this exact "compute Y from X" case and don't have the same
  write-back hazard since they don't imperatively assign to other state.
- If the effect genuinely needs to synchronize two independent pieces of
  state (e.g. an internal value and an external library's state), guard
  the write with a check that it actually changes the value (`if (x !==
  newX) x = newX`), so a no-op write doesn't retrigger the cycle -- Svelte
  effects rerun when a tracked dependency's value changes, so writing the
  same value it already had breaks the cycle.
- For an indirect cycle through a `$derived`, restructure so the effect
  writes to a *different* piece of state than anything the same effect
  (directly or via a derived) reads -- separate the "read triggers" from
  the "write targets" cleanly.
- Use `untrack()` around the specific read that shouldn't establish a
  dependency, when an effect legitimately needs to read a value without
  reacting to its own writes to it -- but scope it to that one read, not
  the whole effect body.

## Pitfalls
- Wrapping the entire effect body in `untrack()` to make the error go away
  removes the effect's reactivity almost entirely, so it stops responding
  to legitimate external changes too -- scope `untrack` narrowly to the
  one problematic read/write pair.
- Adding an equality check everywhere as a reflexive fix can mask a
  design problem where two effects shouldn't be mutually synchronizing
  state at all -- if the equality guard is doing all the work of
  preventing an otherwise-guaranteed loop, consider whether a single
  `$derived` (one-directional) would replace both effects more simply.

## Verify
Reproduce the exact interaction that triggered the freeze/error, confirm
the console no longer floods and `effect_update_depth_exceeded` no longer
appears, and separately confirm the effect still fires the expected
number of times (e.g. once) when the dependency it's meant to react to
actually changes.
