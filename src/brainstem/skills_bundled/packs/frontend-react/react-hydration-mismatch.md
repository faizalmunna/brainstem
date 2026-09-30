---
name: react-hydration-mismatch
description: Diagnose "Text content does not match server-rendered HTML" and related SSR/CSR hydration mismatches in React/Next.js.
triggers: ["hydration mismatch", "hydration error", "text content does not match", "did not match server-rendered html", "hydration failed"]
permissions: ["READ"]
---

## Symptom
React logs a hydration warning/error (`Text content does not match
server-rendered HTML`, `Hydration failed because the initial UI does not
match`) and either the page flickers/re-renders on load, or React
discards the server HTML and re-renders the whole subtree client-side.

## Likely causes
1. **Non-deterministic render inputs** used directly in JSX: `Date.now()`,
   `Math.random()`, `typeof window !== 'undefined'` branches, or reading
   `window`/`navigator` during the render pass instead of in an effect.
2. **Locale/timezone-dependent formatting** (`toLocaleDateString`, `Intl`)
   producing different output on the server (often UTC, a fixed locale)
   than the browser.
3. **Browser-only DOM mutation before hydration** -- browser extensions
   (password managers, grammar checkers) injecting attributes into the
   DOM before React hydrates, so the pre-hydration DOM no longer matches
   what the server sent.
4. **Conditional rendering keyed off `localStorage`/cookies read
   synchronously** on the client but not available during SSR.
5. Invalid HTML nesting from the server (e.g. `<div>` inside `<p>`) that
   the browser silently "fixes" in its parsed DOM tree before React can
   hydrate against it.

## Diagnose
- Check the exact warning text: React usually names the mismatched text
  or attribute, telling you which node to look at first.
- Grep the flagged component tree for `Date`, `Math.random`, `window.`,
  `navigator.`, `localStorage`, `toLocaleString`/`toLocaleDateString`
  used outside a `useEffect`.
- If the mismatch is only in dev tools with a browser extension enabled,
  test in an incognito window with extensions disabled -- this is cause 3,
  not a real bug in the app, and the fix is `suppressHydrationWarning` on
  that specific node, not a rewrite.
- For Next.js App Router, check whether the mismatched value comes from a
  Client Component reading something server-unavailable during its first
  render pass rather than after mount.

## Fix
- Move non-deterministic or browser-only reads into `useEffect` and
  render a stable placeholder (or `null`) until after mount, then update
  state -- this guarantees the first client render matches the server
  render exactly, and the "real" value appears one tick later.
- For locale-sensitive formatting, pass an explicit, fixed locale/timezone
  to `Intl`/`toLocaleDateString` on both server and client, or defer
  formatting to a `useEffect` the same way.
- For the third-party-DOM-injection case specifically, use
  `suppressHydrationWarning` narrowly on the exact element affected --
  don't disable hydration warnings globally, since that hides real bugs
  everywhere else in the tree.

## Pitfalls
- Reaching for `suppressHydrationWarning` as a first fix for causes 1/2/4
  just silences the symptom; the visible flash-of-wrong-content on load
  is still there, it's just no longer logged.
- Wrapping the entire app in a client-only mount check (`if (!mounted)
  return null`) to "fix" one component's mismatch defeats SSR for the
  whole page and hurts LCP/SEO -- scope the fix to the actual component.

## Verify
Reload the page with JavaScript disabled (or view source) and confirm the
server HTML for the affected node matches what appears immediately after
hydration with JS enabled, before any effect has had a chance to run.
