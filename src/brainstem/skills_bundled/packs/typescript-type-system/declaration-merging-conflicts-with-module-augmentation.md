---
name: declaration-merging-conflicts-with-module-augmentation
description: Augmenting a third-party module's types or merging an interface produces a confusing duplicate identifier error or the new fields simply do not appear where expected.
triggers: ["duplicate identifier error typescript module augmentation", "declare module not applying types", "extending express request type not working", "interface merging not working typescript", "augmented types not showing up in autocomplete"]
permissions: ["READ"]
---

## Symptom
A team tries to add a custom field to a library's type (a common example:
adding `req.user` to Express's `Request` interface, or adding a custom
property to `window`) using `declare global` or `declare module
'express'`. Either TypeScript reports `Duplicate identifier 'Request'` /
`Subsequent property declarations must have the same type` at a location
that looks unrelated to the change, or the augmentation compiles fine but
the new field never actually shows up as available on the type where the
developer expected to use it (still shows the original library type,
unaugmented).

## Likely causes
- **The augmentation is written as a plain `interface` redeclaration
  in a regular module file (one with top-level `import`/`export`) instead
  of inside a proper `declare module 'target-module' { ... }` block** --
  TypeScript treats a file with imports/exports as a module, so a
  same-named `interface` in it is a new, unrelated local declaration, not
  a merge with the library's global one; this either silently creates an
  unused duplicate or produces a same-name conflict depending on scope.
- **The augmented interface's property is typed incompatibly with an
  existing declaration for the same property somewhere else in the
  codebase** (two different augmentation files both add `req.user` with
  different types) -- declaration merging requires every merged piece to
  agree exactly on conflicting members' types, and TypeScript's "duplicate
  identifier"/"subsequent declarations must have the same type" errors
  are exactly this disagreement, often between two augmentation files
  neither author knew about the other.
- **The augmentation file isn't included in the `tsconfig.json`'s
  `include`/`files`, or isn't imported/referenced from anywhere the
  compiler actually loads** -- a `.d.ts` augmentation file that TypeScript
  never parses has no effect at all, so the "fix" silently does nothing
  rather than erroring, which looks identical to "the merge didn't work."
- **The augmentation targets the wrong module specifier** -- e.g.
  `declare module 'express'` when the actual runtime type comes from
  `@types/express-serve-static-core` re-exported through `express`, so
  the merge target doesn't line up with the interface actually used at
  the consumption site, and the augmentation silently applies to nothing
  observably used.

## Diagnose
1. Confirm the augmentation file's surrounding syntax: does the file have
   any top-level `import`/`export` outside the `declare module`/`declare
   global` block? If yes and the block is `declare global`, an `export
   {}` statement is required at the end of the file to make TypeScript
   treat it as a module augmentation rather than colliding globally.
2. Run `tsc --noEmit --listFiles` (or check the project's `include` array
   in `tsconfig.json`) to confirm the augmentation `.d.ts` file is
   actually part of the compiled program -- a file with zero references
   and not covered by `include` patterns is silently ignored.
3. Grep the whole repo for other `declare module 'same-target'` blocks or
   other declarations of the same interface member -- most "duplicate
   identifier" errors trace to a second, forgotten augmentation
   elsewhere (often in a different package in a monorepo) declaring the
   same field with a slightly different type.
4. Check the exact module specifier being augmented against where the
   consuming code actually imports its types from -- open the library's
   own `.d.ts` (via "go to definition" on the type at the consumption
   site) to see which module the base interface is truly declared in.

## Fix
Put augmentations in a dedicated `.d.ts` file that is unambiguous about
its intent: for augmenting a module's exported types, use `import
'target-module'; declare module 'target-module' { interface Request {
user?: User; } }` (the leading side-effect `import` ensures TypeScript
treats the file as augmenting that specific module rather than creating
an unrelated global one). For augmenting truly global ambient types
(like `Window`), use `declare global { interface Window { myFlag: boolean;
} } export {};` -- the trailing `export {}` is what tells TypeScript the
file is a module (required for `declare global` to mean "merge into the
global scope" rather than "this is itself the global scope"). Ensure the
file is covered by `tsconfig.json`'s `include`, and centralize all
augmentations for one target module in exactly one file so conflicting
re-declarations can't accumulate across the codebase unnoticed.

## Pitfalls
Don't work around a stubborn duplicate-identifier error by casting to
`any` at the call site (`(req as any).user`) -- that abandons the actual
goal of the augmentation (typed access to the new field) and reintroduces
an untyped boundary exactly where the team was trying to add safety. Also
avoid scattering module augmentations for the same third-party library
across multiple files/packages in a monorepo "because it was convenient
at the time" -- even when each individual augmentation is internally
valid, multiple independent authors are highly likely to eventually
declare the same member with subtly different types, reproducing this
exact bug later.

## Verify
After consolidating the augmentation into one correctly-scoped file, run
`tsc --noEmit` project-wide and confirm no duplicate-identifier errors
remain anywhere. Then, at a real consumption site (e.g. inside an Express
route handler), hover the augmented property (`req.user`) and confirm the
editor shows the intended custom type, not `any` and not a "property does
not exist" error -- this confirms the merge is actually visible at the
point of use, not just internally consistent in the declaration file.
