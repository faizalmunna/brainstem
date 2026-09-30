---
name: array-object-mutation-defeats-readonly-covariance
description: A function typed to take a readonly array or object still lets a caller pass a mutable one that later gets mutated elsewhere, causing a value to change out from under code that assumed it was stable.
triggers: ["readonly array still got mutated", "typescript readonly not actually preventing mutation", "array covariance bug typescript", "passed mutable array to readonly parameter", "value changed unexpectedly after being passed as readonly"]
permissions: ["READ"]
---

## Symptom
A function is carefully typed to accept `ReadonlyArray<T>` (or `readonly
T[]`, or a `Readonly<SomeObject>`) specifically so it can safely hold
onto a reference and assume the contents won't change later -- for
example, storing it in a cache, a memoization key, or comparing it by
reference across renders/ticks. Despite the `readonly` typing, the stored
value's contents do change later, causing stale-comparison bugs or
memoization that returns wrong cached results, because the *caller*
still has (and uses) a mutable reference to the exact same array/object
and pushes/mutates it after the call.

## Likely causes
- **TypeScript's `readonly` on a parameter type only prevents *that
  function* from calling `.push()`/reassigning properties through that
  specific reference/parameter -- it does not make the underlying object
  immutable, and does not restrict what the original mutable reference
  the caller holds can still do to the same object.** Arrays and object
  types in TypeScript are covariant for `readonly` purposes: a `T[]` is
  assignable to a `ReadonlyArray<T>` parameter precisely because
  TypeScript only checks that the callee won't mutate through that
  binding, not that no other binding exists.
- **The function stores the reference itself (in a `Map`, a class field,
  a closure) rather than a copy**, so any mutation the original caller
  performs on their own mutable variable -- even long after the function
  call returned -- is visible through the stored reference, since both
  point at the identical runtime object.
- **A nested property of a `Readonly<T>`-typed object is itself a mutable
  array or object**, and `Readonly<T>` in TypeScript's standard library is
  shallow -- it marks only the top-level properties read-only, not
  anything nested inside them, so `readonlyConfig.items.push(x)` compiles
  and mutates successfully even though `readonlyConfig` itself looks
  fully protected at a glance.
- **A `readonly` array/tuple is deliberately cast back to mutable**
  somewhere in the chain (`as T[]`, or spread into a new mutable array
  and then that copy is discarded while the original reference is kept
  around and mutated) to satisfy some other API that wants a plain
  mutable array, silently reopening the exact hole `readonly` was meant
  to close.

## Diagnose
1. Confirm the actual bug is reference-sharing, not a typing gap per se:
   log/inspect object identity (`===`) between the value observed as
   "changed" and the original object the caller mutated -- if they're the
   same reference, this confirms shared mutable state is crossing the
   `readonly` boundary as expected by the language, not a compiler bug.
2. Trace where the "readonly" value is stored after the function call
   returns (a cache, a memo, a field) and check whether it stores the
   reference directly or makes a defensive copy (`[...items]`,
   `structuredClone`, `Object.freeze`d clone) at the point of storage.
3. For nested-mutation cases, check each property of the `Readonly<T>`-
   typed object individually -- specifically whether any property is
   itself an array, `Map`, `Set`, or plain object, since `Readonly<T>`'s
   shallowness means only primitive-valued top-level properties are
   actually protected from any angle.
4. Grep for `as` assertions or spreads near the boundary that might be
   converting a `readonly` type back to mutable, or for the *caller's*
   continued use of the same variable after passing it in (does the
   caller's code path call `.push()`/mutate the same variable later in
   the same function?).

## Fix
Where true immutability (not just a one-sided typing hint) is required --
caching, memoization keys, anything compared by reference over time --
make a real defensive copy at the point of storage, not just a
`readonly`-typed parameter: shallow-copy with spread/`Array.from` for
one level, or a structural clone for nested data, and consider
`Object.freeze()` (which does enforce actual runtime immutability,
shallowly, and throws or silently no-ops on mutation attempts in strict
mode) if the risk of accidental caller-side mutation is high enough to
warrant a runtime guard rather than relying on the type system alone,
which -- as this skill describes -- only advises the callee, not the
caller. For deep immutability guarantees, use a recursive `DeepReadonly`
utility type as *documentation and callee-side protection*, while still
pairing it with an actual deep clone at the storage boundary if the
data must not change out from under stored consumers.

## Pitfalls
Don't treat adding `readonly`/`Readonly<T>` to a parameter type as
sufficient protection against the exact bug in this skill's symptom --
it's real protection against the *callee* accidentally mutating, but
provides zero protection against a *caller* mutating their own retained
reference afterward, which is a fundamentally different guarantee that
requires a copy, not a type annotation. Also avoid reaching for
`Object.freeze()` on large or deeply nested objects as a default
habit without checking the performance cost and confirming freezing is
actually shallow unless recursively applied -- a frozen top-level object
with a still-mutable nested array gives the same false sense of safety
`Readonly<T>` does.

## Verify
Reproduce the original bug scenario (caller mutates their reference after
passing it in) against the fixed code and confirm the stored/cached value
no longer changes -- specifically check object identity (`===`) between
the caller's mutable object and the stored one is now `false` (a genuine
copy), not `true`. If `Object.freeze()` was added as a runtime guard, add
a test that attempts a mutation on the frozen object and confirms it
throws (in strict mode) or is silently a no-op, matching what the code
that reads it actually assumes.
