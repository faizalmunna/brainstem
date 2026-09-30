---
name: conditional-mapped-type-explosion-slows-typechecking
description: Deeply nested conditional or mapped types make the editor freeze or tsc take minutes because the type checker is doing exponential work, and error messages stop pointing at anything useful.
triggers: ["typescript type checking extremely slow", "editor freezes on this type", "type instantiation is excessively deep and possibly infinite", "tsc taking forever to compile", "error message is thousands of characters long typescript"]
permissions: ["READ"]
---

## Symptom
Either (a) `tsc --noEmit` or the editor's TypeScript language service
becomes dramatically slower after a change to a shared, heavily-used
utility type -- autocomplete lags by seconds, hovering a type takes
noticeable time, or CI's type-check step goes from tens of seconds to
minutes -- or (b) a specific line produces an error message hundreds or
thousands of characters long, sometimes literally `Type instantiation is
excessively deep and possibly infinite`, that doesn't clearly point at
the actual mistake, forcing the developer to guess rather than read the
error.

## Likely causes
- **A recursive conditional or mapped type has no depth limit and is
  applied to a large or deeply-nested object type**, so the compiler
  recursively re-evaluates the type for every level of nesting -- a
  "deep partial"/"deep readonly" utility type applied to a large state
  tree is a common concrete trigger, since object depth multiplies
  directly into type-checker work.
  applied
- **A generic utility type branches into multiple conditional checks
  that are evaluated per-property in a mapped type**, and the combination
  is exponential in the number of properties/union members rather than
  linear -- e.g. a type that maps over a large union and, for each member,
  runs another conditional against every property of that member.
- **A large union type is used as the source of a mapped type or
  distributive conditional type**, and TypeScript distributes the
  conditional over every member of the union individually -- a union with
  dozens of string-literal members (common with generated API types, or
  enums-as-literal-unions) can turn what looks like one type operation
  into dozens of separate ones under the hood.
- **The slow type is instantiated repeatedly across many files** (a
  shared utility type imported and applied fresh at many call sites)
  rather than computed once and reused, so the real-world cost is the
  per-file instantiation count multiplied by the already-expensive
  single-instantiation cost.

## Diagnose
1. Use `tsc --extendedDiagnostics` (or `--generateTrace <dir>` for a
   detailed trace analyzable with the `@typescript/analyze-trace` tool)
   to get a breakdown of where compile time is actually going -- this
   points at specific files/types rather than requiring a guess.
2. Bisect by commenting out or simplifying recently-changed shared
   utility types one at a time and re-timing `tsc --noEmit` (`time npx
   tsc --noEmit`) to isolate which specific type definition's change
   correlates with the slowdown, rather than assuming it's the most
   recently-touched file.
3. For a specific slow/unreadable-error line, check whether the type
   involved is applied to a large union or a deeply nested object by
   hovering the type arguments in the editor -- if the "input" type has
   dozens of members or many nested levels, that's very likely
   contributing directly to the blowup.
4. Check the utility type's own definition for unbounded recursion (a
   conditional/mapped type that calls itself on a nested property type
   with no depth counter or terminating base case for primitive/leaf
   types).

## Fix
Add an explicit recursion depth limit to recursive utility types using a
counter type parameter that increments each recursive call and bails out
to a simple base type once a small limit (e.g. 5-10) is reached, rather
than recursing until TypeScript's own internal depth limit kicks in and
produces the "excessively deep" error. For types that distribute over
large unions, consider whether the operation genuinely needs to be
per-member -- if not, restructure to operate on the union as a whole
rather than each member individually (e.g. via a mapped type keyed by a
smaller, controlled set of keys instead of distributing over the entire
union). Where a shared utility type is instantiated identically across
many files, consider computing and exporting the resolved type once
(`export type ResolvedFoo = DeepPartial<Foo>;`) so the expensive
computation happens once rather than being re-triggered at every import
site, and prefer a simpler, less general type (a hand-written interface
for the specific shape actually needed) over a maximally-generic
recursive utility type when the generality isn't actually being used.

## Pitfalls
Don't respond to a slow or unreadable type error by reaching for `any`
at the problem site to make the error disappear -- that hides the type
information entirely rather than fixing the performance problem, and
often only relocates the same blowup to wherever that `any` next gets
used against the same underlying deep type. Also avoid adding a depth
limit so low that the utility type silently stops working correctly on
realistic inputs (returning a wrong/incomplete type past the cutoff
without any error) -- verify the chosen limit actually covers the deepest
real object the type will be applied to in the codebase, not just enough
to make the immediate slow case go away.

## Verify
Re-run `tsc --noEmit` with `--extendedDiagnostics` before and after the
fix and compare the reported check time and instantiation count directly
-- a meaningful fix should show a clear drop in both, not just a
subjective "feels faster." For a recursion-depth fix specifically, test
the utility type against the deepest real object type in the codebase
(not just a small example) and confirm it still produces the fully
correct type rather than silently truncating at the new depth limit.
