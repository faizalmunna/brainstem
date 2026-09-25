---
name: callback-parameter-mismatch-not-caught-by-compiler
description: A callback passed where a more specific event or argument type is expected type-checks fine even though its parameter type is a supertype that should have been rejected.
triggers: ["callback type mismatch not caught by typescript", "function parameter bivariance", "event handler typed wrong but no error", "typescript accepted incompatible callback", "strictFunctionTypes not catching this"]
permissions: ["READ"]
---

## Symptom
Code passes a callback like `(event: Event) => void` to an API that
actually invokes it with a more specific subtype, e.g. `(event:
MouseEvent) => void` expected by an `onClick` handler, or a generic
event-bus `subscribe<T>(handler: (payload: T) => void)` called with a
handler typed for a narrower payload than the channel actually carries.
It compiles without complaint, but at runtime the callback accesses a
property that only exists on the narrower type it was written against,
throwing or producing `undefined` when the bus actually delivers the
wider/different real type.

## Likely causes
- **Method-syntax callback parameters are checked bivariantly by
  TypeScript for backward-compatibility reasons, while arrow-function/
  property-syntax callback parameters are checked contravariantly under
  `strictFunctionTypes`** -- a callback type declared as a method
  (`interface Handlers { onEvent(e: SpecificEvent): void }`) accepts a
  handler typed for a broader or narrower event than one declared as a
  property (`interface Handlers { onEvent: (e: SpecificEvent) => void
  }`) would, so two API surfaces that look equivalent at a glance have
  different actual strictness depending on which syntax the library
  author happened to use.
- **`strictFunctionTypes` is off (or the whole `strict` umbrella isn't
  enabled)**, so contravariant parameter checking is skipped for
  function-typed properties too, not just methods -- see the
  strictness-flags skill in this pack for how this can be true without
  the team realizing it.
- **The callback's parameter type is written as a wider type than what
  the calling API actually guarantees**, sometimes deliberately (to reuse
  one handler across multiple slightly-different event sources) -- this
  is only safe if the handler body itself never accesses members outside
  the common/narrower intersection, but nothing enforces that once the
  wider parameter type is accepted.
- **A generic callback-accepting function's type parameter for the
  callback isn't tied tightly enough to the value actually passed to the
  callback at invocation time** (e.g. the subscribe function is typed
  generically over `T` but the actual runtime dispatch doesn't guarantee
  every subscriber receives the same `T` it declared), making the
  mismatch a design gap in the callback-registration API itself, not just
  a call-site mistake.

## Diagnose
1. Confirm `strictFunctionTypes` is actually enabled in the resolved
   `tsconfig` (see the strictness-flags-not-actually-enabled skill's
   diagnostic steps) -- reproduce by temporarily toggling it and checking
   whether the suspect callback assignment newly errors.
2. Check whether the callback-accepting interface/type declares the
   handler using method shorthand (`method(arg: T): void`) versus a
   function-typed property (`method: (arg: T) => void`) -- convert it
   mentally (or in a scratch file) between the two syntaxes and see
   whether TypeScript's acceptance of the mismatched callback changes,
   which confirms bivariance-via-method-syntax as the specific cause.
3. Trace the real runtime type actually delivered to the callback (log
   the argument's actual shape/constructor at runtime, or check the
   event source's documentation) and diff it against the type the
   callback function declares for its parameter -- the gap between "what
   the type system let through" and "what's actually delivered" is the
   concrete bug.
4. Search the codebase for other handlers registered against the same
   event source/bus and compare their parameter types for consistency --
   inconsistent narrowing across handlers for the same source is a strong
   signal this has happened more than once.

## Fix
Where you control the callback-accepting API's type declaration, declare
handler properties using the function-property syntax (`onEvent: (e: T)
=> void`), not method shorthand, so `strictFunctionTypes` actually
applies contravariant checking to it -- this alone converts many silent
mismatches into real compile errors. Ensure `strictFunctionTypes` (or
`strict`) is on project-wide. At call sites, type each callback's
parameter to match the *exact* type the source actually delivers (the
specific event subtype, the specific payload type for that channel),
rather than a convenient broader supertype, even if the handler body
currently only touches common fields -- this protects against a future
edit to the handler body that assumes the narrower type is always safe.
Where one handler is deliberately meant to serve multiple related event
types, make that explicit with a real union parameter type
(`(e: MouseEvent | KeyboardEvent) => void`) and handle both cases in the
body, rather than typing it as the loosest common supertype and hoping
the body never needs the specific fields.

## Pitfalls
Don't respond to a bivariance-related error by switching the interface
back to method shorthand specifically because it's more permissive and
makes the immediate error disappear -- that's choosing the less-checked
syntax to avoid a real, correct compiler objection, not fixing the
mismatch. Also avoid writing the callback parameter as `any` to sidestep
a confusing contravariance error you don't have time to fully understand
-- that removes checking for the callback entirely rather than just for
the one problematic overload/assignment.

## Verify
With `strictFunctionTypes` enabled, run `tsc --noEmit` and confirm the
previously-accepted mismatched callback now either compiles correctly
(because it was retyped to the accurate narrower/union type) or fails
with a clear contravariance error if left unfixed. At runtime, log the
actual delivered argument's shape in the handler once and confirm it
matches the parameter type declared, for at least one real event/payload
observed in a running dev/staging environment, not just inferred from
documentation.
