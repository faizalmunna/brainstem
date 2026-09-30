---
name: any-propagates-from-untyped-boundary
description: Type errors that should exist across a large part of the codebase silently disappear because any from one untyped boundary spreads through inference into unrelated code.
triggers: ["any is spreading through my codebase", "why did type checking stop catching errors here", "JSON.parse result typed as any breaking things downstream", "untyped library causing any everywhere", "type safety silently disabled in this function"]
permissions: ["READ"]
---

## Symptom
A bug that should have been caught by the type checker (calling a method
that doesn't exist, passing a string where a number was expected) makes
it past `tsc --noEmit` cleanly. Tracing backward, the value involved
eventually originates from `JSON.parse()`, a third-party import with no
types (or a hand-written `declare module 'x'` stub that's just `any`), or
a variable explicitly typed `any` several function calls upstream -- and
because `any` disables type checking not just for that value but for
everything it touches or gets assigned into, the loss of safety extends
far past the original untyped call, often across module boundaries the
original author never saw.

## Likely causes
- **`JSON.parse()` returns `any` by design** (its return type in `lib.es5.d.ts`
  is literally `any`, since the shape can't be known statically), and that
  `any` is assigned directly to a variable or destructured without an
  explicit type annotation or runtime validation, so everything derived
  from it inherits `any` silently.
- **A third-party dependency has no type declarations and no `@types/`
  package**, so under default settings it resolves to implicit `any`
  (visible via `noImplicitAny` errors if that flag is on, invisible if
  it's off) -- every function parameter or return value touching that
  library becomes an `any` on-ramp.
- **A hand-written type declaration for an external module is a stub**
  written as `declare module 'legacy-lib';` with no shape, or explicitly
  typed `any` "to get it working," and was never revisited once the
  immediate compile error went away.
- **`any` is being assigned into a variable that itself has no explicit
  type annotation**, letting TypeScript infer the variable's type as
  `any` instead of a real one -- if that variable is then exported or
  passed into other functions, every consumer of it also loses type
  checking, even in files that never directly touch the original
  untyped source.

## Diagnose
1. Enable (or check that) `noImplicitAny` is on in `tsconfig.json`, and
   run `tsc --noEmit` -- this alone surfaces many boundary points where
   `any` is entering implicitly rather than being explicitly requested.
2. Use `tsc --noEmit --listFiles` combined with editor hovering, or the
   `// @ts-expect-error`-driven bisection technique (temporarily
   annotate suspect variables with explicit types and see where errors
   appear), to trace a specific bad value backward through the call chain
   to its origin.
3. Grep the codebase for `JSON.parse(`, `: any`, `as any`, and
   `declare module` to enumerate every explicit and implicit `any`
   on-ramp, then cross-reference which ones feed into the module where the
   uncaught bug occurred.
4. Check whether `strict` mode (or specifically `noImplicitAny` and
   `strictNullChecks`) is actually enabled project-wide versus only in
   parts of the codebase via per-file `// @ts-nocheck` or a looser
   `tsconfig` in a subdirectory -- a partially-strict project lets `any`
   leak across the boundary between strict and non-strict regions
   undetected.

## Fix
Contain `any` at the exact point it enters the system rather than letting
it flow. For `JSON.parse`, write (or use) a small runtime-validating
wrapper that both parses and checks the shape (a hand-rolled type guard,
or a schema-validation library like Zod/io-ts) so the function's return
type is a real, narrow type derived from actual validation, not an
assumed cast. For untyped third-party libraries, write a minimal but real
`.d.ts` covering just the functions/shapes actually used (not a full
stub), or install/author an `@types/` package, so the library boundary
produces real types instead of `any`. In both cases, once the boundary
function has a real return type, explicitly annotate the variable that
receives its result so TypeScript can never widen it back to `any` via
inference even if the boundary changes later.

## Pitfalls
Don't fix a `JSON.parse` boundary by simply writing `JSON.parse(text) as
ExpectedType` -- a type assertion doesn't validate anything at runtime,
so it looks like a fix (the `any` is gone from the type checker's
perspective) while leaving the exact same risk of a real shape mismatch
reaching production uncaught (see the type-assertion-masks-runtime-mismatch
skill in this pack). Also avoid writing an overly broad `.d.ts` stub like
`declare module 'legacy-lib' { const x: any; export = x; }` just to make
`noImplicitAny` stop complaining -- that satisfies the compiler flag
without actually reintroducing any type safety, which is the same failure
mode with an extra step.

## Verify
After adding runtime validation or real type declarations at the
boundary, run `tsc --noEmit` with `noImplicitAny` enabled and confirm the
specific bug that previously passed unnoticed is now a compile error (or,
for the `JSON.parse` case, confirm invalid input at runtime now throws
from the validation layer instead of silently producing a malformed
object). Then grep for other call sites consuming the same boundary
function and confirm none of them needed an explicit `any`/`as` cast
removed to keep compiling -- if they did, they were relying on the same
unsafety and need the same review.
