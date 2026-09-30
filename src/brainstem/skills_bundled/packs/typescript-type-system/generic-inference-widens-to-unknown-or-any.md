---
name: generic-inference-widens-to-unknown-or-any
description: A generic function's type parameter silently infers as unknown, any, or a much wider type than intended depending on how callers invoke it, losing type safety without any compiler error.
triggers: ["generic type parameter inferred as unknown", "generic function losing type safety silently", "typescript generic inference too wide", "why is T any here", "generic returns any instead of the actual type"]
permissions: ["READ"]
---

## Symptom
A generic helper like `function getValue<T>(obj: Record<string, T>, key:
string): T` or a wrapper around `fetch`/a state store is written with a
type parameter that looks like it should track the caller's actual data
type. In practice, at various call sites `T` ends up inferred as
`unknown`, `{}`, or `any` -- and everything downstream of the call type-
checks without complaint even though it's now completely unchecked,
because nothing about the call site forced a good inference and
TypeScript quietly picked the most permissive type that satisfies the
constraints instead of erroring.

## Likely causes
- **No argument in the call site actually constrains `T`**, so TypeScript
  has nothing to infer from and falls back to the type parameter's
  default (if given) or its constraint's upper bound (often `unknown` or
  `{}`), rather than failing -- generics only infer from usage; they don't
  request extra information from the caller.
- **`T` only appears in the function's return position, not in any
  parameter type** -- inference sites are parameters; a type parameter used
  solely in the return type has nothing to infer from unless the caller
  provides it explicitly (`getValue<MyType>(...)`), so it silently
  defaults instead of prompting for an explicit argument.
- **A generic constraint uses `any` somewhere in its definition** (directly,
  or transitively through a chained/piped generic utility), and `any` is
  contagious through generic inference -- once any single inferred slot in
  a chain resolves to `any`, it can propagate into `T` for the whole
  chain regardless of how well-typed the other arguments are.
- **The call passes a value whose own type was already widened** (e.g. an
  untyped `JSON.parse()` result, an `any`-typed third-party return value,
  a spread of a loosely-typed object) directly into the generic call, so
  the generic correctly infers `T` as `any`/`unknown` because that's
  genuinely the type of what was handed to it -- the bug is upstream, not
  in the generic itself.

## Diagnose
1. Hover the call site in the editor (or inspect with `tsc --noEmit
   --explainFiles`/a quick throwaway `const check: ExpectedType =
   result;` assignment) to see exactly what `T` resolved to, rather than
   assuming from the function signature alone.
2. Check whether `T` appears in at least one parameter type of the
   generic's signature -- if it only appears in the return type or in a
   constraint, that's the structural reason inference has nothing to lock
   onto.
3. Trace the actual runtime value being passed backward to its origin --
   if it came from `JSON.parse`, an `any`-typed import, or a library
   without types, the widening is originating there, not in the generic
   wrapper (cross-reference the any-propagation skill in this pack).
4. Temporarily add an explicit type argument at a suspect call site
   (`getValue<ExpectedType>(...)`) and see whether downstream code that
   previously type-checked now shows errors -- if it does, that's proof
   real type information was being silently lost before, not just
   theoretically at risk.

## Fix
Make inference structurally forced rather than optional: ensure `T`
(or each type parameter) appears in at least one parameter position so
callers must supply a value that pins it down, and add a real constraint
(`T extends Record<string, unknown>` rather than an unconstrained `T`, or
`T extends BaseEvent` rather than `T = any`) so that even when inference
has little to go on, the fallback is a meaningful, narrow type instead of
`any`. Where a function's `T` genuinely can't be inferred from any
argument (e.g. a generic factory with no input describing the output
shape), require the type argument explicitly at every call site rather
than giving it a permissive default, so a missing type argument is a
visible, deliberate choice (or a lint/compiler prompt) instead of a silent
`unknown`/`any` fallback.

## Pitfalls
Don't "fix" a too-wide inference by adding a default type parameter of
`any` (`function getValue<T = any>(...)`) -- that removes the visible
symptom (an inference error) while keeping the exact unsafety the skill
describes, just quieter. Also avoid over-constraining `T` to a single
concrete type just to make one call site happy, which defeats the point
of writing a generic in the first place and forces unrelated callers into
awkward casts.

## Verify
Add explicit-argument tests at 2-3 real call sites representing the
range of types actually passed through the generic, run `tsc --noEmit`,
and confirm each resolves to the specific expected concrete type (not
`unknown`/`any`) by checking the inferred type in the editor or via a
`const check: SpecificType = result` assertion line. Then deliberately
pass a wrong-shaped argument at one call site and confirm `tsc --noEmit`
now reports an error there, proving the generic is actually constraining
something instead of accepting everything.
