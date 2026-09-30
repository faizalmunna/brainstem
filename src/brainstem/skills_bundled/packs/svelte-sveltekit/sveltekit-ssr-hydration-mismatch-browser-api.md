---
name: sveltekit-ssr-hydration-mismatch-browser-api
description: Diagnose a SvelteKit hydration mismatch or server crash caused by a browser-only API accessed during component initialization instead of after mount.
triggers: ["window is not defined sveltekit", "hydration mismatch sveltekit", "localStorage is not defined", "referenceerror document is not defined", "sveltekit ssr crash browser api"]
permissions: ["READ"]
---

## Symptom
Either the dev server (or production SSR) throws `ReferenceError: window
is not defined` / `document is not defined` / `localStorage is not
defined`, or the page renders but logs a hydration mismatch and briefly
flashes different content right after load -- traced back to code that
runs in a component's top-level `<script>` block rather than inside
`onMount` or a `$effect`.

## Likely causes
1. **A browser global is read directly in the component's script body**
   (`let width = $state(window.innerWidth)`), which executes during SSR
   as well as on the client -- there is no `window` on the server, so
   this either crashes SSR outright or, if guarded sloppily, produces a
   different initial value server-side vs. client-side.
2. **`localStorage`/`sessionStorage`/cookies read synchronously at init**
   to seed initial state (e.g. a theme preference), so the server always
   renders the default while the client's first paint (before any effect
   runs) briefly shows the stored value, or the read throws entirely
   under SSR.
3. **A non-deterministic value computed at the top level** (`crypto.
   randomUUID()`, `Date.now()`) used directly in markup -- the value
   computed during SSR differs from the value computed again during the
   client's initial render pass, producing a genuine content mismatch
   rather than a crash.
4. **A third-party library that touches `window` as a side effect of
   being imported** (not even called yet) is imported at module scope in
   a file that's also rendered on the server, rather than imported
   dynamically or guarded.

## Diagnose
- Read the exact error/stack trace: a `ReferenceError` during SSR points
  at the file and line directly -- check whether that line is inside
  `onMount`/`$effect` (safe, client-only) or in the component's top-level
  script (runs during SSR too).
- Grep the flagged component for `window.`, `document.`, `localStorage.`,
  `navigator.`, and `sessionStorage.` outside of `onMount(() => {...})`
  or `$effect(() => {...})`.
- Import `browser` from `$app/environment` and check whether the
  offending code already guards on it (`if (browser) { ... }`) -- if it
  does but is still in the top-level script, the guard only prevents the
  crash, not the hydration mismatch, since the client's *first* render
  still differs from the server's.
- For hydration-mismatch-only cases (no crash), compare view-source (SSR
  output) against the DOM immediately after the JS bundle finishes
  hydrating but before any effect fires, to pinpoint the exact node.

## Fix
- Move any browser-only read out of the component's top-level script and
  into `onMount` or `$effect`, initializing the `$state` variable to a
  neutral, SSR-safe default first, then updating it once the effect runs
  -- this guarantees the server render and the client's first render
  match exactly, with the "real" value appearing one tick later.
- For values that must be known before first paint to avoid a visible
  flash (like a stored theme), do the read in `+layout.server.js` via
  cookies (which SSR *can* see) instead of `localStorage` (which it
  can't), so the correct value is part of the server-rendered HTML from
  the start.
- For non-deterministic values needed in markup, generate them once on
  the server (in `load`) and pass them down as data, rather than
  computing them independently on each side.
- Guard module-scope side effects from third-party libraries with a
  dynamic `import()` inside `onMount`, or check `browser` from
  `$app/environment` before the import executes.

## Pitfalls
- Guarding a browser read with `if (browser)` inside the top-level script
  stops the crash but not the mismatch -- the server still renders the
  "false" branch's output, and the client's first render (before any
  effect) also does, so the fix looks complete until the value that
  matters visually changes right after load in a way users notice as a
  flash; the effect-based deferral is what actually fixes the mismatch.
- Reaching for `{#if browser}...{/if}` around large chunks of markup to
  sidestep the whole problem disables SSR for that entire section,
  hurting first-paint content and SEO for something that usually only
  needed one value deferred, not a whole subtree.

## Verify
Run the SSR build (or dev server) and load the page with JavaScript
disabled to confirm no crash and that the server-rendered HTML is
sensible; then reload with JavaScript enabled and confirm no hydration
warning appears in the console and no visible flash occurs before the
deferred value updates.
