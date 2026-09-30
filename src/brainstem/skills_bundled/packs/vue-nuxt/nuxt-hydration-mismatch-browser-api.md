---
name: nuxt-hydration-mismatch-browser-api
description: Fix Nuxt SSR crashes or hydration warnings caused by code that reads window, document, or localStorage during server render.
triggers: ["window is not defined nuxt", "hydration mismatch nuxt", "localStorage is not defined ssr", "nuxt ssr crash browser api", "hydration node mismatch"]
permissions: ["READ"]
---

## Symptom
Either the Nuxt dev server or build crashes with `ReferenceError: window
is not defined` / `localStorage is not defined`, or the app builds fine
but the browser console logs a hydration mismatch and part of the page
flickers or gets discarded and re-rendered right after load.

## Likely causes
1. **Code directly referencing `window`, `document`, `localStorage`, or
   `navigator`** during `setup()` or at the top level of a component/
   plugin that also executes on the server, where those globals don't
   exist.
2. **A third-party library that touches `window` at import time** (not
   just when called), pulled in as a regular plugin/import instead of a
   client-only plugin (`*.client.ts`).
3. **Content that legitimately differs between server and client** --
   `Date.now()`, `Math.random()`-based IDs, or locale/timezone-dependent
   formatting -- producing different output in the server-rendered HTML
   than in the client's first render pass, without ever throwing, just
   mismatching.
4. **An incorrect or missing `import.meta.client`/`import.meta.server`
   guard**, or a guard placed in a `computed` that gets evaluated during
   SSR anyway because it's accessed eagerly rather than deferred to after
   mount.

## Diagnose
- If it's a hard crash, the stack trace names the exact file and line
  reading the browser global -- start there, don't assume it's the
  component you were last editing.
- If it's a hydration warning without a crash, read the exact node/text
  React... er, Vue names in the console warning; it tells you which
  DOM subtree mismatched.
- Temporarily set `ssr: false` for the specific route (via `definePageMeta`
  in a `NuxtPage` context is not supported per-route the same as Next, so
  instead wrap the suspect component in `<ClientOnly>` temporarily) to
  confirm the mismatch disappears -- if it does, you've isolated the
  component at fault.
- Run `curl` or "View Page Source" on the SSR'd page and compare the raw
  HTML against what's in the DOM immediately after hydration (before any
  effect runs) for the affected element.

## Fix
Guard any browser-only read with `import.meta.client` and move it into
`onMounted` so it never executes during SSR and the first client render
matches the server render exactly (render a stable placeholder until the
mounted value is available). For libraries that touch `window` on import,
register them as a `.client.ts` plugin so Nuxt only loads them in the
browser. For non-deterministic content, either compute it consistently on
both sides (fixed locale/timezone) or defer it to `onMounted` the same
way. Use `<ClientOnly>` only around the specific subtree that genuinely
cannot render server-side, not the whole page.

## Pitfalls
Wrapping an entire page (or the root layout) in `<ClientOnly>` to make one
broken widget stop erroring throws away SSR for the whole page -- slower
first paint, worse SEO -- when the actual fix only needed to scope to the
one component reading `window`. Similarly, reaching for
`suppressHydrationWarning`-style `<ClientOnly fallback>` tricks for a
non-deterministic-value mismatch (cause 3) hides the warning but the
visible flash of different content on load is still there.

## Verify
Run a production build (`nuxi build && node .output/server/index.mjs` or
`nuxi generate` for static) and load the page fresh: confirm no
`ReferenceError` in server logs, no hydration warning in the browser
console, and that "View Page Source" HTML for the affected element
matches what's visible immediately after hydration, before any mounted
hook has had a chance to update it.
