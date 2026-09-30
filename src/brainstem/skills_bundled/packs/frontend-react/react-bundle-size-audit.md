---
name: react-bundle-size-audit
description: Diagnose why a React app's JavaScript bundle is larger than expected and reduce it without breaking functionality.
triggers: ["bundle too big", "bundle size", "javascript bundle bloat", "app loads slowly", "lighthouse bundle size warning", "code splitting"]
permissions: ["READ"]
---

## Symptom
Lighthouse/PageSpeed flags a large JavaScript bundle, initial page load is
slow on throttled connections, or the bundle noticeably grew after adding
what seemed like a small feature/dependency.

## Likely causes
1. **A large dependency imported for one small piece of functionality**
   (e.g. an entire date library, icon set, or utility library imported
   wholesale instead of the specific functions used) that doesn't
   tree-shake because of how it's imported.
2. **No code splitting** -- the entire app (including rarely-visited
   routes, admin-only screens, heavy modals) ships in the main bundle
   instead of being loaded on demand.
3. **Client Components (Next.js) or otherwise-unnecessary client-side
   code pulling in server-only or heavy dependencies** that never needed
   to reach the browser at all.
4. **Duplicate versions of the same dependency** bundled because of
   mismatched versions across the dependency tree (common with
   monorepos/multiple packages depending on different major versions of a
   shared library).
5. **Unused exports/dead code not eliminated** because of side-effectful
   module patterns that prevent the bundler's tree-shaking from proving
   the code is safe to remove.

## Diagnose
- Run a bundle analyzer (`next build` + `@next/bundle-analyzer`,
  `source-map-explorer`, or webpack-bundle-analyzer for non-Next setups)
  and look at the largest modules by actual shipped size, not just
  dependency count.
- For a specific dependency that looks large, check its import style:
  `import _ from 'lodash'` vs `import debounce from 'lodash/debounce'`,
  or whether the library ships an ESM build that tree-shakes at all.
- Check for duplicate entries of the same package at different versions
  in the analyzer output (a strong signal of a dependency-resolution
  issue, not a code issue).
- Diff bundle size before/after a recent change that's suspected of
  causing a regression, to isolate which addition caused it.

## Fix
- Import only what's used from large utility libraries (named/path
  imports instead of importing the whole library), or switch to a
  smaller, tree-shakeable alternative if the library doesn't support
  partial imports well.
- Code-split rarely-visited routes/heavy components with dynamic
  `import()` (or the framework's built-in lazy-loading, e.g. Next.js's
  automatic per-route splitting, `next/dynamic` for heavy client
  components) so they load on demand instead of in the initial bundle.
- Audit Client Component imports for anything server-only or unnecessary
  on the client, and move it behind a boundary that doesn't ship it to
  the browser (see `nextjs-server-client-boundary`).
- Deduplicate dependency versions (lockfile resolution overrides, or
  aligning versions across a monorepo's packages) when the analyzer shows
  the same library shipped twice.

## Pitfalls
- Lazy-loading everything indiscriminately trades initial bundle size for
  more network requests and potential loading-state jank on interaction --
  prioritize splitting genuinely large, rarely-needed-immediately code
  (heavy editors, charts, admin panels), not every small component.
- Switching to a "smaller" alternative library without checking API
  compatibility can introduce subtle behavior differences (locale
  handling, edge-case formatting) that only surface later -- verify
  output equivalence for the specific usage, not just bundle size.

## Verify
Re-run the bundle analyzer after the change and confirm the specific
module(s) targeted actually shrank or moved into an on-demand chunk, and
re-run Lighthouse/PageSpeed to confirm the initial-load JavaScript size
metric improved, not just that the change "felt" smaller.
