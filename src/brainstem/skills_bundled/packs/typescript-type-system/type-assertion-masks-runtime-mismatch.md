---
name: type-assertion-masks-runtime-mismatch
description: A value cast with an as assertion type-checks perfectly but throws or produces wrong data at runtime because the assertion was never actually true.
triggers: ["as cast hiding a bug", "type assertion caused runtime error", "cannot read property of undefined after as SomeType", "as any then real crash later", "typescript compiled fine but crashed at runtime"]
permissions: ["READ"]
---

## Symptom
Code somewhere does `const user = response.data as User;` (or `<User>
response.data`, or a chained `as unknown as User`). It compiles cleanly
and passes review because the shape "looks right" to the author. Weeks
or months later, in production, code that reads `user.profile.avatarUrl`
throws `Cannot read properties of undefined`, or a computed value is
silently wrong -- because the actual runtime object never had a
`profile` field, or had it under a different shape, and the `as`
assertion told the compiler to simply trust the author instead of
verifying anything.

## Likely causes
- **The assertion was written to satisfy an API response whose real
  shape drifted after a backend change**, and nothing re-validates the
  assertion against the new shape -- assertions have no runtime effect at
  all, so a backend contract change produces zero compile errors and zero
  test failures unless something actually inspects the value at runtime.
- **The assertion is bridging a genuinely different type through `as
  unknown as X`**, a double-assertion specifically used to bypass
  TypeScript's normal "these types have no overlap" safety check -- this
  pattern is a strong signal the author already knew the compiler
  wouldn't accept a single-step assertion, meaning the types are further
  apart than a simple cast should paper over.
- **The assertion narrows a union down to one member** (`(action as
  AddAction).payload`) based on an assumption about which branch the code
  is in, without an actual runtime discriminant check -- if the assumption
  is wrong (a caller reaches this code path with a different union
  member), the cast doesn't just fail to help, it actively suppresses the
  type error that would have caught the mistake.
- **The assertion was copy-pasted from a similar-looking call site** whose
  actual runtime value has a different origin/shape than the new call
  site's value, carrying over a cast that happened to be safe in the
  original context but isn't in the new one.

## Diagnose
1. Grep the file/module for `as ` and `<Type>value`-style assertions and
   list every one -- each is a point where the compiler's normal checking
   was overridden by the author's claim, and any of them is a candidate
   for this bug, not just the one that already crashed.
2. For each suspect assertion, find where the underlying value actually
   originates (an API call, `JSON.parse`, a third-party callback) and
   compare its real runtime shape (log it, inspect a captured payload, or
   check the actual API/library documentation or OpenAPI schema) against
   the asserted type field by field.
3. Check whether the assertion is a double assertion through `unknown`
   (`as unknown as X`) -- treat every instance of this pattern in the
   codebase as higher-risk by default, since it exists specifically to
   suppress a compiler objection about type overlap.
4. Reproduce with the actual malformed/unexpected payload (from a bug
   report, a log, or a staging environment) fed through the code path
   without the assertion (temporarily remove it and see what type error
   TypeScript now reports) to see exactly what the assertion was hiding.

## Fix
Replace the assertion with a runtime check that produces the same
narrowed type through actual verification instead of a claim. For a
value shape, use a type guard function (`function isUser(x: unknown): x
is User { return typeof x === 'object' && x !== null && 'id' in x && ...
}`) or a schema-validation library (Zod, io-ts, valibot) that both
validates and returns a properly-typed result, so a shape mismatch throws
or returns a typed error at the boundary instead of flowing silently
downstream. For narrowing a union based on an assumed variant, replace
the cast with an actual discriminant check (`if (action.type === 'add')`)
so the narrowing is real and the `default`/`else` branch can handle (or
assert-never) the case where the assumption doesn't hold. Where an
assertion is unavoidable (e.g. bridging a genuinely-guaranteed-safe
boundary like a `Object.keys` result), keep it minimal (single-step, not
double-through-`unknown`) and comment exactly why it's provably safe at
that call site.

## Pitfalls
Don't respond to a caught mismatch by adding a broader assertion further
upstream (`as any`) to make the immediate error go away -- that expands
the blast radius of exactly the problem this skill describes instead of
fixing it (see the any-propagation skill in this pack). Also avoid
replacing every assertion with a runtime check that only logs a warning
and continues with the unsafely-cast value anyway -- if the check doesn't
actually stop bad data from propagating (via a thrown error, an Either/
Result-style return, or a fallback default), it's cosmetic and the
original bug can still occur.

## Verify
Remove the assertion, add the runtime type guard or schema check in its
place, then feed the code path both a valid payload and the actual
malformed payload that triggered the original bug (from a log or bug
report) and confirm the malformed one is now caught explicitly (a thrown
validation error, a handled error branch) rather than silently flowing
through as if it were valid. Run `tsc --noEmit` to confirm the narrowed
type from the guard satisfies every downstream usage without needing a
new assertion anywhere else in the same flow.
