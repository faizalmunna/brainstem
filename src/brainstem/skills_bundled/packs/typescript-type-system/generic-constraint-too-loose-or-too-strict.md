---
name: generic-constraint-too-loose-or-too-strict
description: A generic function's extends constraint either lets clearly invalid types compile without error or rejects legitimately valid callers that should be accepted.
triggers: ["generic constraint rejecting valid type", "T extends constraint too strict", "generic accepts type it shouldn't", "why does this type satisfy the constraint", "narrowing a generic constraint breaks callers"]
permissions: ["READ"]
---

## Symptom
Two opposite-looking complaints trace back to the same root skill: (1) a
generic function typed `function process<T extends object>(item: T)`
happily accepts arrays, functions, class instances, or other values that
are technically `object` but clearly weren't the intended input, and
some downstream logic that assumed a plain record breaks at runtime; or
(2) a generic typed with a specific-looking constraint like `T extends
{ id: string }` rejects a perfectly valid caller's type at the call site
with an assignability error that looks wrong to the caller, because their
type "obviously" has an `id` field and they can't see why TypeScript
disagrees.

## Likely causes
- **The constraint used a broad built-in type (`object`, `{}`, `Record<string,
  any>`) as a stand-in for "some kind of plain data object,"** but none of
  those actually mean that in TypeScript -- `{}` means "anything except
  `null`/`undefined`," `object` includes arrays, functions, and class
  instances, and `Record<string, any>` requires an index signature that
  most concrete interfaces don't actually declare, so the constraint
  either lets in far more than intended or rejects normal interfaces that
  don't structurally match an index signature.
- **The constraint is written against an interface with methods/behavior
  the caller's type doesn't need to satisfy for the generic to work
  correctly**, over-constraining based on what one reference implementation
  happened to have rather than what the generic function actually uses
  from `T` -- rejecting valid callers whose type is a strict subset of
  what's genuinely required.
- **The constraint's shape and the caller's actual type differ in
  read-only/mutability, or in exact vs. excess properties, in a way that's
  only visible via a full structural diff** -- e.g. the constraint expects
  a mutable array (`T extends unknown[]`) but the caller passes a
  `readonly` tuple, or the constraint requires an exact literal type where
  the caller's inferred type has been widened to a plain `string`.
- **The constraint was copied from a similar generic elsewhere in the
  codebase without re-deriving it from what this specific function body
  actually does with `T`** -- constraints should be derived bottom-up from
  actual usage inside the function, and a copy-pasted constraint often
  carries over requirements (or omits necessary ones) that don't match
  the new function's real needs.

## Diagnose
1. For an over-permissive constraint, construct a deliberately "wrong"
   value that still satisfies it (an array for an `object` constraint, a
   function for a `{}` constraint) and confirm it's accepted -- this
   proves the constraint's actual boundary, rather than relying on
   the shape it looks like it should express.
2. For an over-restrictive constraint, take the rejected caller's type and
   diff it property-by-property against the constraint's declared shape
   (including modifiers: `readonly`, optional `?`, exact literal vs.
   widened type) -- the mismatch is usually one specific property's
   modifier or literal-vs-widened distinction, not the type being
   "completely wrong."
3. Read the actual function body and list every property/method of `T`
   it genuinely accesses -- compare that list against the constraint;
   anything in the constraint not in that list is over-constraining,
   and anything accessed but not in the constraint means the constraint
   is under-specified (likely papered over with an internal `as` cast).
4. Check whether the constraint was written before or after the function
   body, if history/blame is available -- constraints retrofitted onto an
   already-written generic are more likely to be copy-pasted
   approximations rather than derived from actual usage.

## Fix
Derive the constraint bottom-up from exactly what the function body uses
from `T`, expressed as the narrowest interface that covers that usage --
if the function only reads `.id` and `.name`, constrain to `{ id: string;
name: string }`, not a larger domain interface that happens to have those
fields plus many more. This simultaneously fixes both directions: it
naturally excludes arrays/functions/unrelated objects (they won't
structurally have the exact needed shape) without accidentally excluding
any caller type that genuinely has the needed fields, regardless of what
other fields or methods that caller's type also happens to carry. Where
mutability matters, be explicit about `readonly` in the constraint only if
the function body genuinely never mutates `T`; where literal specificity
matters, constrain with a generic default and a second type parameter
(`function process<T extends string, K extends T = T>`) rather than
hard-coding one literal shape.

## Pitfalls
Don't fix an over-restrictive constraint by weakening it all the way to
`any`/`unknown` just to make the immediate caller compile -- that
re-opens the over-permissive failure mode for every other caller instead
of fixing the actual mismatch for this one. Conversely, don't fix an
over-permissive constraint by switching to a giant union of every
concrete type currently passed to the function -- that's not a
constraint, it's an enumeration that breaks the moment a new valid caller
type is added elsewhere, defeating the point of writing a generic at all.

## Verify
After narrowing the constraint to match actual usage, run `tsc --noEmit`
across every existing call site and confirm all previously-valid callers
still compile without new errors, and that the previously-accepted
invalid values (arrays, unrelated objects) used in the diagnose step now
correctly fail to satisfy the constraint. Add one deliberately-wrong call
site as a `// @ts-expect-error` line in a type-level test if the project
has one, so a future loosening of the constraint that re-admits the
invalid case is caught automatically.
