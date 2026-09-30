---
name: sveltekit-prerender-dynamic-route-failing
description: Diagnose a SvelteKit dynamic route that fails to prerender at build time or silently produces a 404 for a static deployment.
triggers: ["sveltekit prerender failing", "entries function not found", "prerender dynamic route 404", "sveltekit build skips route", "prerender crawl not discovering page"]
permissions: ["READ"]
---

## Symptom
Running `svelte-kit build` (or `vite build`) with `export const prerender
= true` set on a dynamic route (`/blog/[slug]`) either fails outright
during the build, or completes but the deployed static site 404s when a
visitor navigates directly to one of the expected slugs.

## Likely causes
1. **No `entries()` export (or `config.entries`) tells SvelteKit which
   param values exist.** For a static site, there's no request at build
   time to derive `[slug]` from -- without an explicit list of values,
   SvelteKit's crawler can only discover the route by following links
   from pages it already knows about, and won't invent param values on
   its own.
2. **The route's `load` function reads request-only data** -- `cookies`,
   request headers, `url.searchParams` that vary per real visitor, or
   `locals` populated by an auth hook -- inside a load path marked for
   prerendering. Prerendering runs once at build time with no real
   request context, so code that assumes a live request either crashes
   or produces one fixed (wrong) result baked into the static output for
   every visitor.
3. **A page is only ever linked to via client-side navigation logic**
   (a button calling `goto()`, not an `<a href>`), so SvelteKit's link
   crawler never discovers it during the build even though `entries()`
   would have worked for other pages -- it needs to be listed explicitly
   in `entries()` or in `config.kit.prerender.entries` in
   `svelte.config.js`.
4. **The load function needs a live database/secret not available in the
   build environment** (e.g. a CI build running without the same env vars
   as the runtime server), so the failure looks like a SvelteKit
   prerendering bug but is actually a missing-configuration issue specific
   to the build step.

## Diagnose
- Read the exact build error: SvelteKit's prerender step reports which
  route failed and often why (e.g. "not found," a thrown error from
  load, or a warning about a route with dynamic parameters and no
  `entries`).
- Check the route's `+page.js`/`+page.server.js` (or the parent
  `+layout`) for an `entries` export; if it's a server load, note that
  `entries()` lives in the corresponding `+page.server.js` or a shared
  `+page.js`, matching where `prerender` is declared.
- Grep the load function for `cookies.`, `request.headers.`, or
  `locals.` -- any of these being read on a code path that also runs
  during prerendering is a red flag for cause 2.
- After a build that "succeeds," check the actual output directory (or
  the deployed site) for the specific route's HTML file -- if it's
  missing despite no build error, the crawler simply never found it
  (cause 3), which is a silent-skip rather than a failure.
- Confirm the CI/build environment has the same environment
  variables/secrets the load function needs, separate from the runtime
  server's environment.

## Fix
- Add an `entries()` function returning every valid param combination
  (e.g. fetched from the same data source the pages themselves use, or a
  static list) so the prerenderer knows exactly which pages to generate.
- Guard any request-dependent read in a prerendered load path, or split
  the route so the parts that need a real request aren't prerendered
  (`export const prerender = false` for that specific segment, or move
  the personalized part to run client-side after a static shell loads).
- For pages not reachable via a normal `<a href>` link, add their paths
  explicitly to `entries()` or to `kit.prerender.entries` in
  `svelte.config.js` so the crawler includes them even without a
  discoverable link.
- Ensure the build pipeline has access to the same environment
  configuration the load function needs, or fetch the data needed for
  `entries()`/prerendering from a source that's available at build time
  specifically (not just at runtime).

## Pitfalls
- Setting `prerender = 'auto'` or disabling prerendering entirely for a
  route just to make the build pass hides a real gap in `entries()` and
  quietly turns a route that should be static into one served
  dynamically (which may not even be possible on a purely static
  deployment target) -- diagnose why the crawler/entries list is
  incomplete instead of turning prerendering off wholesale.
- Hardcoding a small sample list in `entries()` to get the build to pass
  locally and forgetting to wire it to the real, complete data source
  before deploying results in a production site missing most of its
  dynamic pages.

## Verify
Run a full production build, inspect the generated output directory for
an HTML file per expected param value from `entries()`, and serve the
static output locally to confirm navigating directly to one of those
URLs (not just via in-app links) returns the correct prerendered page
rather than a 404.
