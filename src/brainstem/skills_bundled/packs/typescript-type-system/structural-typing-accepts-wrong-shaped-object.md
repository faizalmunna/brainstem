---
name: structural-typing-accepts-wrong-shaped-object
description: A function typed to accept one specific interface silently accepts an object built for a completely different purpose because the shapes happen to overlap.
triggers: ["typescript let the wrong object through", "duck typing bug typescript", "why does this compile it's not the right type", "structural typing accepted wrong object", "excess property check didn't catch this"]
permissions: ["READ"]
---

## Symptom
A function declared as `function charge(order: Order)` compiles fine when
called with a `Invoice` object, a test fixture, or some other unrelated
type that was never intended to be an `Order` -- and at runtime it fails
or behaves wrong because the object is missing behavior the caller
assumed came with the `Order` type, or has a field with the same name but
different meaning (e.g. both have `id: string`, but one is a UUID and the
other a human-readable order number). No compiler error appears anywhere
in the chain, because TypeScript checks structure, not declared identity.

## Likely causes
- **TypeScript uses structural (duck) typing, not nominal typing** -- two
  interfaces with the same member names and compatible types are
  mutually assignable even if they represent conceptually unrelated
  domain concepts and were never meant to be interchangeable.
- **The target type is a subset of a larger object's shape**, so passing
  a big "god object" (a full Redux state slice, an ORM entity with 40
  columns) into a function typed to want only 3 of those fields type-checks
  trivially, and it becomes easy to pass the wrong big object as long as it
  happens to carry those 3 field names too.
- **The excess-property check, which normally catches this for object
  literals, only runs on literals passed directly as an argument** -- once
  the value is assigned to an intermediate variable or comes from a
  function return, TypeScript falls back to plain structural compatibility
  and stops flagging extra/mismatched-purpose properties entirely.
- **Optional fields widen compatibility further than intended** -- a type
  with several optional properties is structurally compatible with almost
  any object that happens to satisfy the required subset, making it easy
  for an object from a different domain to slip through if it coincidentally
  has none of the fields that would have been required.

## Diagnose
1. Find the call site and check whether the argument is a literal passed
   inline (excess-property checking applies) or a variable/return value
   (it doesn't) -- reproduce by inlining the object literal directly at
   the call site and see if TypeScript starts complaining about excess or
   mismatched properties.
2. Run `tsc --noEmit` with `--strict` on and diff against the current
   config; confirm `strictNullChecks` isn't papering over the fact that
   optional fields are doing the widening (see the tsconfig-strictness
   skill in this pack for the general check).
3. Use the "declare and hover" trick: assign the suspect argument to a
   `const check: Order = suspiciousValue;` line temporarily at the call
   site and hover/inspect the inferred type error (or lack of one) to see
   exactly which members TypeScript considers satisfied and which, if any,
   are the actual mismatch.
4. Grep for other places the same "victim" type (`Order`) is constructed
   or annotated, and diff their shapes against the type actually flowing
   in -- structural bugs are almost always visible once you put both
   shapes side by side.

## Fix
Introduce nominal typing where domain identity matters, not just shape.
The standard TypeScript pattern is a "branded" or "tagged" type: add a
unique, otherwise-unused discriminant property (often typed as a unique
symbol or literal string) that only the correct constructor path can
produce, e.g. `type Order = { __brand: 'Order'; id: string; ... }`. This
makes the type only satisfiable by values that were actually constructed
as an `Order`, because a plain object literal or a differently-branded
type won't have that exact tag, and structural compatibility now
requires the brand to match. For simpler cases where a full brand is
overkill, tightening the function signature to require enough
distinguishing required fields (rather than relying on 1-2 common ones)
reduces the collision surface even without full nominal typing.

## Pitfalls
Don't reach for `as Order` to silence the mismatch once you notice it --
that's a type assertion, not a fix, and it actively hides the exact bug
this skill is about (see the type-assertion-masks-runtime-mismatch skill
in this pack). Also avoid branding every single type in the codebase
reflexively: branding adds real friction (every legitimate construction
site needs an explicit cast to attach the brand), so reserve it for types
where distinct-but-structurally-similar values genuinely get confused in
practice, not as a blanket policy.

## Verify
Add the brand (or tightened required fields) and confirm the specific
call site that previously compiled with the wrong object now fails
`tsc --noEmit` with a clear "missing property `__brand`" or similar
structural mismatch error, then fix that call site to construct/obtain a
real `Order` and re-run `tsc --noEmit` clean across the whole project to
confirm no other call site was relying on the same accidental
compatibility.
