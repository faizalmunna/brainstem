---
name: narrowing-lost-in-closure-or-callback
description: A typeof or truthiness check narrows a variable correctly on the next line but TypeScript widens it back to its original type inside a nested function or callback.
triggers: ["typescript narrowing not working inside callback", "typeof check not narrowing in arrow function", "object is possibly undefined inside settimeout", "narrowed type reverts inside closure", "strictNullChecks error inside callback despite check above"]
permissions: ["READ"]
---

## Symptom
Code checks `if (typeof value === 'string')` or `if (user != null)`, and
immediately below the check, `value`/`user` is correctly narrowed to
`string` or the non-null type. But inside a `setTimeout`, a `.then()`
callback, an event handler, or any other nested function defined within
that same `if` block, TypeScript reports the variable back as
`string | undefined` (or the original union), producing a
`strictNullChecks` error the developer thinks should already be
resolved by the guard a few lines above.

## Likely causes
- **The narrowed variable is a `let`-bound outer variable (or a mutable
  object property), and TypeScript cannot prove it isn't reassigned
  between the check and the time the callback actually runs** -- narrowing
  is a static, control-flow-based analysis, and TypeScript deliberately
  discards narrowing for any binding a nested function closes over if that
  binding is mutable, because the callback could execute asynchronously
  after further reassignment.
- **The value being checked is a property access** (`obj.prop`) rather
  than a local variable, and TypeScript only narrows property-access
  expressions within the same synchronous control flow -- once you cross
  into a callback, even a synchronous one like `.forEach()`, property
  narrowing on `obj.prop` is not retained because `obj` could theoretically
  be mutated or the getter could return something different on next access.
- **The check happens on a `const`-like value that TypeScript should be
  able to retain, but the callback's parameter or a `this`-bound context
  shadows or re-derives the value** rather than closing over the exact
  already-narrowed binding, so it's actually a different (unnarrowed)
  reference, not a real narrowing-loss bug.
- **The callback is typed with a very loose parameter type** from a
  library's own type definitions (e.g. an event handler typed to receive
  `any`), and the "loss" is actually the callback boundary re-widening the
  type via its own declared signature, not TypeScript discarding narrowing
  at all.

## Diagnose
1. Confirm the exact declaration kind of the narrowed variable: `let`
   or `const`. Reproduce by changing a suspect `let` to `const` (or copying
   it into a new `const` right after the guard) and checking whether the
   error disappears inside the callback -- if it does, this confirms
   reassignment-safety is the reason, not a TypeScript bug.
2. For property-access narrowing losses, assign `const narrowedValue =
   obj.prop;` immediately after the guard and use `narrowedValue` inside
   the callback instead of re-accessing `obj.prop` -- if this resolves it,
   the cause is property narrowing not surviving into the closure.
3. Hover the callback's parameter/closed-over variable in the editor (or
   check `tsc --noEmit` output directly) to see the exact type TypeScript
   believes it has at that point, and compare it to the type right after
   the guard, to confirm exactly where the widening happens.
4. Check whether the callback is passed to a third-party function whose
   `.d.ts` declares a broader parameter type than expected -- if so, the
   loss is coming from that boundary's declared type, not from narrowing
   analysis at all.

## Fix
Capture the narrowed value into a new `const` binding immediately after
the guard, and reference only that new binding inside the callback --
this works because TypeScript's flow analysis only discards narrowing for
bindings that could still change; a fresh `const` copy is provably
immutable for the rest of its scope, so its narrowed type is preserved
into any closure that captures it, synchronous or asynchronous. For
object properties specifically, destructure the needed property into a
local `const` right after the check rather than re-reading `obj.prop`
later. If the value is genuinely mutable and must be re-read inside the
callback (e.g. a class field that legitimately changes), re-run the same
type guard inside the callback itself instead of relying on the outer
check -- that gives TypeScript an accurate narrowing point at the moment
it's actually needed.

## Pitfalls
Don't reach for a non-null assertion (`value!`) inside the callback just
to silence the error -- that discards the compiler's legitimate warning
that the value really could have changed by the time an async callback
runs, and can convert a caught compile-time gap into an actual runtime
`undefined` crash if the reassignment genuinely happens before the
callback fires. Also avoid narrowing into a `const` copy so early in a
long function that it goes stale relative to intentional later
reassignments of the original variable -- the copy should be made as
close to the point of use as reasonably possible, not hoisted to the top
of the function out of habit.

## Verify
After introducing the `const` capture, run `tsc --noEmit` and confirm the
specific error at the callback site is gone without adding any `!`
assertion or `as` cast. Then check the surrounding code for a legitimate
reassignment path (search for other assignments to the same `let` binding
in the enclosing scope) to confirm the fix didn't just hide a real race
where the value could actually be different by the time the callback
executes.
