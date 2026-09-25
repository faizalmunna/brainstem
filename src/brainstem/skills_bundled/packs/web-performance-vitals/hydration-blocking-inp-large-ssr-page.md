---
name: hydration-blocking-inp-large-ssr-page
description: Fix clicks that silently do nothing for a moment right after a server-rendered page appears loaded because hydration hasn't finished attaching event handlers.
triggers: ["button does nothing right after page loads", "SSR page not interactive yet", "hydration taking too long", "clicks ignored after page appears loaded", "INP bad only on first interaction"]
permissions: ["READ"]
---

## Symptom
A server-rendered page (Next.js, Nuxt, SvelteKit, etc.) visually appears
fully loaded almost immediately, but the very first click/tap a user makes
in the first second or two either does nothing or responds only after a
noticeable delay -- INP is disproportionately bad specifically for the
*earliest* interaction on the page, while later interactions on the same
page are fine, distinguishing this from a generically heavy handler that's
slow every time.

## Likely causes
1. **The page has a large hydration payload** (a lot of interactive
   components, large embedded JSON state) and the framework must process
   all of it in one synchronous pass before any handler is attached
   anywhere on the page, even for a component the user isn't touching.
2. **The user interacts with an element before its JS bundle has even
   finished downloading/parsing**, common on slower connections/devices
   where the visual HTML (already painted from SSR) is misleadingly ahead
   of the JS readiness.
3. **Hydration mismatches force a full re-render/re-hydration of a
   subtree** instead of the cheap "attach listeners" path, because the
   server-rendered markup didn't exactly match what the client would have
   rendered.
4. **No progressive/selective hydration** -- the framework hydrates the
   entire page as one unit rather than prioritizing the components the
   user is most likely to interact with first (above-the-fold, or
   whichever they actually touch).

## Diagnose
- In DevTools > Performance, record a trace from navigation through the
  first user interaction and look for a long task labeled with the
  framework's hydration function (e.g. `hydrateRoot`, `mountComponent`)
  overlapping with or shortly before the interaction's Input Delay phase.
- Check the gap between the "visually complete" marker (a paint timing or
  manual visual comparison) and `DOMContentLoaded`/the framework's
  hydration-complete event -- a large gap confirms the page looks ready
  before it's actually interactive.
- Use the web-vitals library's attribution build for INP and check
  whether the worst INP entries cluster at the very start of the
  session (first interaction) versus being spread evenly -- clustering at
  the start points at hydration specifically.
- Check the console/framework devtools for hydration mismatch warnings,
  which indicate cause 3 rather than pure payload size.

## Fix
Reduce how much synchronous work stands between "page looks ready" and
"page can actually respond," and where full elimination isn't possible,
make sure the interactive elements users touch first are ready first.
Concretely: use selective/progressive hydration (React Server Components
plus `Suspense` boundaries with client islands, Astro/Qwik-style
resumability, or a framework's built-in lazy-hydration primitives) so
below-fold or rarely-touched components don't block hydration of the
above-fold interactive elements; reduce the embedded state payload passed
from server to client to only what's actually needed client-side, cutting
the parse/reconcile cost; fix hydration mismatches at the source (ensure
server and client render identical output, e.g. avoid `Date.now()` or
`Math.random()` in render, or environment-dependent branches) rather than
letting the framework silently repair them at hydration cost; and where
none of the above is enough, show a genuinely non-interactive visual state
(disabled-looking button, subtle loading affordance) until hydration
completes, so the visual and functional readiness aren't in conflict.

## Pitfalls
- Reducing hydration cost by removing `Suspense` boundaries and hydrating
  everything eagerly "to avoid complexity" reintroduces the exact
  all-at-once hydration cost this fix addresses -- selective hydration is
  the point, not incidental.
- Silencing hydration mismatch warnings (e.g. `suppressHydrationWarning`)
  instead of fixing the underlying server/client render divergence hides
  the symptom in the console while leaving the extra re-render cost in
  place.
- Adding a loading overlay to mask unresponsiveness without actually
  reducing hydration cost improves perceived behavior but not the
  underlying INP metric field data is measuring.

## Verify
Re-run the same trace and confirm the first interaction's Input Delay/
Processing time no longer overlaps a long hydration task, and check
real-user INP field data (CrUX or `web-vitals` attribution) specifically
for the first-interaction cohort to confirm it improved, not just the
lab-measured average.
