---
name: pwa-offline-fallback-design
description: Design a genuinely useful offline experience for a PWA (a real fallback page/state) instead of letting the browser's default "no internet" error show, or showing a fallback that's misleadingly empty.
triggers: ["offline page design", "pwa offline experience", "browser default offline error", "app shows blank screen offline", "no internet connection pwa"]
permissions: ["READ"]
---

## Symptom
When a user loses connectivity, the PWA either shows the browser's
generic "No internet connection" error page (meaning the service worker
isn't intercepting navigation requests to serve anything better), or
shows a mostly-blank/broken page because the app shell loaded from cache
but the data it expected to fetch failed silently with no offline-aware
handling.

## Likely causes
1. **No service worker fetch handler for navigation requests**, so a page
   load while offline goes straight to the browser's own network-error
   page instead of being intercepted and served from cache/a fallback.
2. **The app shell is cached and loads, but individual data fetches
   inside it fail without any offline-specific handling** -- components
   show a generic error, an infinite loading spinner, or silently render
   with missing/undefined data, rather than a clear "you're offline, here's
   what's available" state.
3. **No distinction made between "fully available offline" content
   (previously cached and viewable) and "requires network" content** --
   the UI doesn't tell users which parts of the app they can still use
   versus which parts need a connection.
4. **The offline fallback page itself isn't cached ahead of time**, so if
   the user's very first visit happens while offline (or the fallback
   page was never pre-cached during install), even the fallback fails to
   load.

## Diagnose
- Use browser devtools' network throttling ("Offline" mode) to reproduce
  navigation while offline and observe whether the browser's default
  error page appears (confirms no service worker navigation handling) or
  a custom page appears.
- With the app shell loaded, go offline and trigger a data-dependent
  action (a fetch button, a page requiring live data) and observe the
  actual failure mode -- spinner forever, silent blank state, or an
  explicit "offline" message.
- Check the service worker's `install` event to confirm whether an
  offline fallback page/asset is pre-cached, versus only being cached
  reactively after a user visits it while online.

## Fix
- Add a `fetch` event handler in the service worker for navigation
  requests that falls back to a cached offline page when the network
  request fails, so users get a designed experience instead of the
  browser's generic error.
- Pre-cache the offline fallback page (and its critical assets) during
  the service worker's `install` event, so it's available even on a
  user's very first, possibly-offline visit.
- Design data-fetching components to explicitly detect and handle offline
  failures (checking `navigator.onLine` and/or catching the specific
  network error) and show a clear, honest state ("You're offline -- showing
  the last saved version from [time]" or "This needs a connection to
  load") rather than a generic error or an endless spinner.
- Clearly indicate in the UI which content is available offline (already
  cached, fully interactive) versus which requires a connection, so users
  aren't surprised by what does and doesn't work.

## Pitfalls
- A generic "You're offline" message with no indication of what still
  works undersells a PWA that actually has meaningful offline
  capability -- be specific about what's available, not just that
  something went wrong.
- Silently serving stale cached data with no indication it might be
  outdated (rather than an explicit offline indicator) can mislead users
  into acting on information that's no longer current -- always
  distinguish "live" from "cached/possibly stale" in the UI when offline.

## Verify
Go fully offline (devtools network throttling, or airplane mode on a
real device) and walk through the app's critical flows: confirm
navigation shows the designed offline experience (not the browser
default), confirm data-dependent views show clear, honest offline states,
and confirm previously-cached content remains genuinely usable.
