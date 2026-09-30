---
name: service-worker-stale-content
description: Diagnose a PWA serving stale content (old JS/CSS/HTML) to users after a deploy because the service worker cache isn't updating as expected.
triggers: ["pwa showing old version", "service worker not updating", "users seeing stale content", "cache not busting pwa", "app not updating after deploy"]
permissions: ["READ"]
---

## Symptom
After deploying a new version of the app, some users continue to see the
old version -- stale JavaScript, CSS, or HTML -- sometimes indefinitely,
sometimes only until they manually close all tabs or clear their browser
cache, which most users won't know or bother to do.

## Likely causes
1. **A caching strategy (cache-first) applied to the app shell/JS/CSS
   without a versioning or update mechanism**, so once cached, those
   files are served from cache indefinitely regardless of what's actually
   deployed.
2. **The new service worker is installed but not activated** -- by
   default, a new service worker waits in the "waiting" state until all
   tabs using the old one are closed, so a long-lived tab (common for
   PWAs that stay open) can keep the old service worker (and its cache)
   active indefinitely.
3. **The service worker file itself is cached by the browser's HTTP
   cache** with long-lived cache headers, so the browser doesn't even
   fetch the *new* service worker script promptly, delaying the whole
   update-detection process.
4. **No user-facing update prompt**, so even when a new version is ready
   to activate, users have no signal or easy action to trigger it,
   relying entirely on the passive close-all-tabs behavior.

## Diagnose
- Check the caching strategy applied to app-shell resources (JS/CSS/HTML)
  in the service worker: cache-first with no cache-busting/versioning is
  the direct cause of "never updates without manual intervention."
- Check the HTTP response headers for the service worker script itself
  (`sw.js` or equivalent) -- it should have `Cache-Control: no-cache` (or
  a very short max-age) so browsers check for updates promptly; a long
  `max-age` here delays the whole update cycle at the source.
- In browser devtools' Application/Service Worker panel, check whether a
  new service worker is stuck in "waiting" state, confirming the
  activation-timing cause.
- Confirm whether the app has any `skipWaiting`/update-prompt logic at
  all, or relies entirely on default browser behavior.

## Fix
- Use a cache strategy appropriate to each resource type: versioned/
  hashed asset filenames (which most modern build tools produce)
  combined with a cache-first strategy work well for those specific
  files (since a new deploy produces new filenames, avoiding staleness by
  construction), while the service worker script and the main HTML entry
  point should use network-first or no caching at all, so updates are
  detected promptly.
- Ensure the service worker script itself is served with `no-cache` (or
  short max-age) headers so the browser checks for a new version on each
  visit rather than serving a stale cached copy of the worker itself.
- Implement an explicit update flow: detect a waiting service worker
  (the `updatefound`/`statechange` events), and either call
  `skipWaiting()` combined with `clients.claim()` for an immediate,
  automatic update, or show a "new version available, refresh to update"
  prompt and call `skipWaiting()` on user action -- choose deliberately
  based on whether silent auto-update or explicit user consent fits the
  app.
- Version cache names in the service worker (`caches.open('app-v3')`)
  and delete old-named caches in the `activate` event, so switching
  versions doesn't leave orphaned old caches accumulating.

## Pitfalls
- Calling `skipWaiting()` unconditionally on every install without
  `clients.claim()` can leave open tabs running old page JavaScript
  talking to a new service worker's cache/API expectations, causing
  inconsistent behavior -- pair the two, or reload the page after
  activation, so the whole picture (page JS + service worker) updates
  together.
- Silent, automatic updates (no user prompt) can interrupt a user
  mid-task if the update causes any in-flight state to be lost on
  reload -- for apps with significant in-progress user state, an explicit
  "update available" prompt the user can act on when ready is often
  safer than forcing an immediate reload.

## Verify
Deploy a visibly different version (a version string shown in the UI, for
example), keep an old tab open, and confirm the update-detection/prompt
flow correctly surfaces and applies the new version without requiring the
user to manually clear cache or close all tabs.
