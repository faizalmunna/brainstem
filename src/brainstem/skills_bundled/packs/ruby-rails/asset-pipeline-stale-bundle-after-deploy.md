---
name: asset-pipeline-stale-bundle-after-deploy
description: Fix users seeing an old JavaScript or CSS bundle after a Rails deploy despite the asset pipeline generating new fingerprinted files.
triggers: ["users seeing old javascript after deploy", "sprockets serving stale asset", "webpacker cache not busting", "stale css after rails deploy", "importmap serving old file", "asset not updating after release"]
permissions: ["READ"]
---

## Symptom
After deploying a Rails release with real frontend changes, some users
(or all users for a window of time) keep executing old JavaScript or
seeing old CSS -- errors reference functions/selectors that were removed
in the deploy, and a hard-refresh or private window "fixes" it for that
one user, which points at caching rather than the deploy itself failing.

## Likely causes
1. **Multiple app servers behind a load balancer serve requests during a
   rolling deploy, and the HTML response (with asset fingerprints baked
   into `<script>`/`<link>` tags) came from a *new* server while a static
   asset request lands on an *old* server that hasn't finished deploying
   yet** (or vice versa) -- for a window during rollout, HTML and assets
   are out of sync.
2. **A CDN or reverse proxy in front of the app caches asset responses
   (or the HTML page itself) longer than the deploy cycle**, and its
   cache wasn't invalidated/purged as part of the deploy, so it keeps
   serving the previous release's fingerprinted files (or, worse, the
   previous HTML referencing them) past their intended lifetime.
3. **`public/assets/.sprockets-manifest-*.json` (or the Webpacker/
   `packs-manifest.json` equivalent) wasn't regenerated or wasn't shared
   correctly across app servers** -- e.g. `assets:precompile` ran on only
   one server/container in a multi-instance deploy, or a shared/NFS
   `public/assets` path wasn't updated atomically, so different servers
   serve manifests pointing at different fingerprinted filenames for the
   "same" logical asset.
4. **Fingerprinting itself didn't change because the source file's
   content hash is unaffected by a change to an imported dependency that
   Sprockets/Webpacker doesn't track as a dependency edge** (a common gap
   with vendored/external files, or import maps pointing at
   non-fingerprinted CDN URLs cached by the browser's own HTTP cache).
5. **The browser cached the *HTML page* itself** (not just the asset) due
   to missing/incorrect `Cache-Control` headers on the HTML response, so
   the browser never even requests the new HTML that would reference the
   new fingerprinted asset filenames.

## Diagnose
- Compare the asset fingerprint referenced in the HTML `<script>`/`<link>`
  tag a user's browser actually loaded (view-source or browser devtools
  Network tab) against the fingerprint currently in
  `public/assets/.sprockets-manifest-*.json` or `public/packs/manifest.json`
  on the current release -- a mismatch confirms stale HTML, not just a
  stale asset.
- Check response headers for the HTML page and for the asset request
  itself (`Cache-Control`, `ETag`, `Age`, any CDN-specific header like
  `CF-Cache-Status` or `X-Cache`) to identify whether a CDN/proxy served
  a cached copy rather than hitting the app.
- During the next deploy, watch whether `assets:precompile` runs on every
  app server/container independently, or is expected to run once and be
  shared -- if shared via a volume or object storage, confirm all
  instances see the update at the same moment, not staggered.
- If using import maps or a CDN-hosted dependency, check whether that
  specific file's URL includes a version/content hash at all -- an
  unversioned CDN URL can be cached indefinitely by the browser regardless
  of anything the Rails app does.

## Fix
- Ensure `assets:precompile` (or the JS bundler's build step) runs as
  part of the release *before* traffic is routed to new instances, with
  the compiled output either baked into the deployed artifact/image
  (preferred -- avoids a shared-filesystem race entirely) or pushed to
  a shared/object store atomically before any instance serves from it.
- Set long-lived, immutable `Cache-Control` headers
  (`public, max-age=31536000, immutable`) on fingerprinted asset files
  specifically (safe because the fingerprint changes when content
  changes), but short or no-cache headers on the HTML document itself, so
  browsers always fetch fresh HTML that then references the correct,
  aggressively-cacheable fingerprinted assets.
- If a CDN sits in front of the app, invalidate/purge its cache for the
  HTML paths (not the fingerprinted asset paths, which don't need
  purging if they're content-addressed) as an explicit deploy step.
- For a true zero-downtime rolling deploy, keep the previous release's
  compiled assets available and served alongside the new release for a
  transition window (common with `public/assets` retaining N previous
  precompiles, or a CDN/object-store path per release) so in-flight
  requests referencing old fingerprints during the rollout window don't
  404.

## Pitfalls
- Purging the CDN cache for *all* paths including the fingerprinted asset
  URLs is unnecessary and creates a thundering-herd of cache misses right
  after every deploy -- only the HTML/entry-point paths need purging;
  content-addressed asset URLs are safe to cache forever.
- Precompiling assets on a single "primary" server and relying on a
  shared filesystem mount to distribute them introduces a race during
  rolling deploys where some servers see a partially-written manifest --
  prefer baking assets into the deployable artifact per instance instead.
- Setting `Cache-Control: no-store` on the HTML to "be safe" also disables
  the browser's back/forward cache and beneficial revalidation, hurting
  perceived performance -- `no-cache` (revalidate every time) is usually
  what's actually wanted, not `no-store`.

## Verify
Perform a real rolling deploy (or a close staging simulation) and, during
the rollout window, repeatedly fetch the app's homepage from multiple
concurrent requests, checking that each response's referenced asset
fingerprints exist and are servable (200, not 404) at the moment they're
requested. After the deploy settles, confirm via browser devtools that a
fresh (non-cached) load of the HTML references the new fingerprints and
that the corresponding asset responses carry long-lived immutable cache
headers.
