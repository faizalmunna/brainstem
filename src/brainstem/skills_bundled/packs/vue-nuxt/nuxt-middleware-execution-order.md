---
name: nuxt-middleware-execution-order
description: Diagnose Nuxt route middleware that runs in a different order than expected, causing redirects or auth checks to fire late.
triggers: ["nuxt middleware wrong order", "middleware runs twice nuxt", "global middleware before page middleware", "auth middleware runs too late", "navigateTo not stopping middleware"]
permissions: ["READ"]
---

## Symptom
A named or global Nuxt route middleware runs before or after another
middleware in a different order than the file names or
`definePageMeta({ middleware })` array would suggest -- an auth check
appears to run after a redirect already happened, or a redirect
middleware seems to fire twice on one navigation.

## Likely causes
1. **Global middleware (files ending `.global.ts` in `middleware/`)
   always run on every route change, in alphabetical order, before any
   page-specific middleware** declared via `definePageMeta` -- an
   assumption that a global and a non-global middleware interleave by
   filename doesn't hold; the global/page-specific split is a hard
   boundary.
2. **A layout's own `definePageMeta` middleware runs at a different point
   in the pipeline** than the page's own middleware, surprising anyone
   who assumed layout and page middleware interleave strictly by file
   name across both.
3. **A middleware calls `navigateTo()` without `return`ing it**, so
   execution falls through into the next middleware in the chain even
   though a redirect was already triggered -- looking like the "wrong"
   middleware ran, or ran twice, when really the redirecting one just
   didn't stop.
4. **The same middleware is registered both as global and attached
   explicitly per-page**, causing it to execute twice on the same
   navigation.

## Diagnose
- Add `console.log('middleware:<name>', to.path)` as the very first line
  of every suspected middleware and watch the exact printed sequence
  (server terminal and browser console) during one navigation -- this
  gives the real order directly instead of inferring it from behavior.
- List the files in `middleware/` and note which end in `.global.ts`
  versus which are only referenced from `definePageMeta` -- the global
  ones always run first, in alphabetical order among themselves.
- Grep for `navigateTo(` calls inside middleware and check each one is
  preceded by `return`.

## Fix
Design around the documented order rather than fighting it: global
middleware (alphabetical by filename) always runs before page-specific
middleware. If you need to control order strictly within the global
group, use numeric filename prefixes (`01.auth.global.ts`,
`02.analytics.global.ts`) -- but don't expect that numbering to interleave
with page middleware, which is a separate stage. Always `return
navigateTo(...)` (or `return abortNavigation()`) so the chain halts
immediately instead of continuing into subsequent middleware. Remove
duplicate registration where a middleware is both global and manually
attached per page -- pick one.

## Pitfalls
Renaming middleware files purely to force a particular ordering, without
understanding the global-versus-page-specific split, fixes the immediate
case but breaks again the next time someone adds a new global middleware
whose alphabetical position collides with the assumption baked into the
old names.

## Verify
Trigger the navigation that previously misbehaved and confirm, from the
logged sequence, that each middleware runs exactly once, in the intended
order, and that a redirecting middleware halts the chain -- no
subsequent middleware's log line should appear after its redirect fires.
