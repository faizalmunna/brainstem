---
name: numeric-enum-reverse-mapping-surprises
description: A numeric TypeScript enum behaves unexpectedly at runtime because it silently generates a reverse number-to-name mapping that shows up in iteration, serialization, or bundle size.
triggers: ["enum showing up twice in Object.keys", "numeric enum reverse mapping bug", "enum values appearing in for in loop unexpectedly", "should I use enum or union type typescript", "const enum vs enum bundle size"]
permissions: ["READ"]
---

## Symptom
Code iterates over a numeric enum's keys (`Object.keys(Status)` or a
`for...in` loop) expecting to get just the member names (`Active`,
`Inactive`), but the array/loop also includes the numeric values
themselves as string keys (`'0'`, `'1'`), roughly doubling the expected
entries. Or, a numeric enum value is serialized to JSON/sent over an API
and the receiving side gets a bare number (`0`) with no indication of
which named member it represents, breaking a UI or log that expected the
human-readable name. Or, someone notices a non-`const` enum produces a
surprisingly large amount of generated JavaScript compared to a simple
union type.

## Likely causes
- **Numeric enums (not string enums, not `const enum`) compile to an
  object literal that TypeScript populates with both directions of the
  mapping** -- `Status.Active` gives `0`, but the compiled object also
  gets `Status[0] === 'Active'` added automatically, so any code that
  treats the enum object as a plain dictionary of just its declared
  members (`Object.keys`, `for...in`, `JSON.stringify(Status)`) sees both
  the forward and reverse entries, not just the ones written in source.
- **The enum value crosses a serialization boundary** (stored in a
  database as an integer, sent as JSON) where only the bare number
  survives -- unlike a string-literal union (`'active' | 'inactive'`),
  a numeric enum's on-the-wire representation carries no indication of
  which name it corresponds to unless the receiving system also has
  the exact same enum definition to map it back.
- **A non-`const` enum is used purely for compile-time convenience but
  is emitted as a full runtime object with helper code**, unlike a
  `const enum` (inlined, no runtime object at all) or a union-of-literals
  (zero runtime footprint, pure type), so codebases that reach for
  `enum` reflexively pay a real (if usually small) bundle-size and
  runtime-object cost that a type-only union wouldn't.
- **`const enum` is used but the project compiles with `isolatedModules`
  (common with esbuild/SWC/Babel-based toolchains, including most modern
  bundlers and ts-jest configurations) or ships declaration files for
  external consumers**, both of which are explicitly incompatible with
  `const enum` inlining -- `const enum` requires whole-program type
  information the single-file transpilers used by those tools don't have,
  producing either a build error or, worse, a silently wrong inlined
  value if the transpiler guesses.

## Diagnose
1. Check the enum declaration: is it `enum Status { Active, Inactive }`
   (numeric, auto-assigned) or does it have explicit string values (`enum
   Status { Active = 'ACTIVE' }`)? Only auto-numeric (or explicitly
   numeric) enums get the reverse mapping; string enums do not.
2. Reproduce by running `Object.keys(YourEnum)` or `console.log(YourEnum)`
   in isolation and visually confirm whether numeric-string keys appear
   alongside the name keys -- this is a two-second, conclusive check.
3. If using `const enum`, check the build toolchain: grep
   `tsconfig.json` for `"isolatedModules": true` and check whether the
   actual bundler/transpiler used in CI is `tsc` directly or a
   single-file transpiler (esbuild, SWC, Babel) -- the latter combination
   with `const enum` is a known incompatibility worth confirming directly
   against the project's real build command, not just assumed.
4. For a serialization concern, trace one enum value from creation
   through to wherever it's persisted/transmitted and check what type
   the receiving schema/consumer expects -- a number with no shared enum
   definition on the other side is a latent bug even if nothing has
   broken yet.

## Fix
For anything that crosses a serialization boundary (API payloads,
database columns, log lines a human needs to read), prefer a string
enum (`enum Status { Active = 'ACTIVE' }`) or, more idiomatically in
modern TypeScript, a plain union of string literals (`type Status =
'active' | 'inactive'`) paired with an `as const` object if named
constants are still wanted (`const Status = { Active: 'active',
Inactive: 'inactive' } as const;`) -- both avoid the reverse-mapping
object entirely and carry a self-describing value across any boundary
without needing the receiving side to share the same enum definition.
Reserve numeric (non-const) `enum` for genuinely internal, in-process-only
values where the reverse mapping is actually useful (e.g. converting a
stored number back to a name for a debug label) and the bundle-size/
runtime-object cost is acceptable. If a `const enum` is desired for its
zero-runtime-cost inlining, only use it when the project's actual build
pipeline is confirmed to run full `tsc` type-checking (not an isolated
single-file transpiler) end to end.

## Pitfalls
Don't "fix" the `Object.keys` double-entry problem by filtering out
numeric-looking keys at every call site (`Object.keys(Status).filter(k
=> isNaN(Number(k)))`) -- that's a workaround for a specific symptom that
has to be repeated everywhere the enum is iterated, rather than removing
the actual cause; switching to a string enum or literal union removes the
need for the filter everywhere at once. Also don't mix `const enum` and
regular `enum` inconsistently across a shared library boundary -- a
`const enum` exported from a package and consumed by a downstream project
with `isolatedModules` will fail to build for consumers even if the
library's own build works fine.

## Verify
After migrating a numeric enum to a string enum or literal union, run
`Object.keys`/`JSON.stringify` on the replacement and confirm only the
intended named entries appear (no numeric-string duplicates). Run
`tsc --noEmit` across all consumers of the old enum to confirm every
comparison/switch/assignment still type-checks against the new
string-based values (numeric literal comparisons like `status === 0`
will now correctly fail to compile, which is the intended signal to
update them to the new string values). For a `const enum` build-tool
concern, run the project's actual production build command (not just
`tsc --noEmit`) end to end and confirm no inlining-related errors or
warnings appear.
