---
name: build-tool-migration-pitfalls
description: Migrate a package (or a whole monorepo) between build tools (e.g. webpack to Vite/esbuild) without silently changing runtime behavior that the old tool happened to provide.
triggers: ["webpack to vite migration", "build tool migration", "esbuild migration issues", "switching bundlers", "migration broke production build"]
permissions: ["READ"]
---

## Symptom
After migrating a package's build tooling (webpack to Vite/esbuild, or
similar), the build succeeds and most functionality appears to work, but
something subtle breaks in production that wasn't caught by local
testing -- an environment variable that's suddenly `undefined`, a CSS
ordering/specificity change, a dynamic import that resolves differently,
or a dependency that behaved differently under the old bundler's specific
handling of it.

## Likely causes
1. **Different environment variable injection behavior** -- webpack's
   `DefinePlugin`-based `process.env.X` replacement and Vite's
   `import.meta.env`-based approach (or its own `process.env` shimming)
   have different rules about what gets replaced at build time versus
   left as a runtime lookup, silently breaking code that assumed the old
   tool's specific behavior.
2. **CSS/asset ordering differences** -- the new tool may bundle/order
   CSS differently (per-component vs. one global bundle, different
   chunking), changing which rule wins when specificity ties, producing
   subtle visual regressions that don't show up as build errors.
3. **A dependency relying on a bundler-specific quirk** (a CommonJS/ESM
   interop edge case webpack handled leniently that the new tool is
   stricter about, or vice versa), breaking only for that specific
   package's import pattern.
4. **Dynamic `import()` chunking behavior differing**, changing which
   code ends up in which chunk and, in edge cases, load-order-dependent
   behavior that happened to work under the old chunking strategy.
5. **Dev-server-only behavior differences** (HMR edge cases, proxy
   configuration syntax) mistaken for production build issues, or vice
   versa -- conflating the two makes diagnosis harder.

## Diagnose
- Reproduce the regression in production-equivalent mode for the new
  tool specifically (a production build, not just the dev server), since
  dev and production pipelines can differ significantly and testing only
  in dev mode misses production-only issues.
- For environment-variable issues, check exactly which variables the new
  tool actually replaces at build time and how (Vite requires an explicit
  `VITE_` prefix or explicit `define` configuration, for example) versus
  what the old configuration assumed.
- For CSS/asset issues, compare the actual generated output bundle
  structure (chunk boundaries, CSS file count/order) between old and new
  tools for the specific affected page.
- For a specific misbehaving dependency, check its own migration notes/
  known-issues for the new bundler -- many popular libraries document
  known bundler-specific quirks.

## Fix
- Explicitly configure environment variable handling to match the
  actual intended behavior under the new tool (correct prefixing,
  explicit `define`/`envPrefix` configuration) rather than assuming
  parity with the old tool's defaults.
- Audit and, if needed, explicitly configure CSS ordering/chunking
  strategy in the new tool to match intended cascade behavior, treating
  a visual regression here as a real bug, not a cosmetic afterthought.
- For a dependency with a known bundler-specific issue, apply the
  documented workaround (an alias, a specific import path, a
  configuration flag) rather than reverting the whole migration for one
  problematic dependency.
- Test the actual production build output (not just dev-server behavior)
  as part of the migration's acceptance criteria, including a full
  regression pass of critical user flows, not just "the build succeeded."

## Pitfalls
- Treating "the build completes without errors" as sufficient
  verification misses the class of bug this migration is most prone to:
  silent runtime/behavioral differences that don't manifest as a build
  failure.
- Migrating an entire large monorepo's build tooling in one atomic change
  makes it hard to isolate which specific package/configuration caused a
  given regression -- migrate incrementally (one package/app at a time,
  if the tooling allows both to coexist temporarily) where feasible.
- Copying webpack-specific configuration patterns into the new tool's
  config format without understanding whether they're still necessary
  can carry forward workarounds for problems the new tool doesn't
  actually have, adding unnecessary complexity.

## Verify
Run a full production build with the new tool, deploy it to a staging
environment, and exercise the application's critical user flows manually
or via the E2E suite -- specifically including any flow that touches
environment-variable-dependent behavior, CSS-sensitive UI, and any
dependency flagged during the diagnose step -- before considering the
migration complete for that package.
