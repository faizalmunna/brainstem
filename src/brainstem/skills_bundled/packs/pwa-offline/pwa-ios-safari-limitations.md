---
name: pwa-ios-safari-limitations
description: Diagnose PWA features that work on Android/desktop but fail or behave differently on iOS Safari, due to iOS's specific PWA/service-worker restrictions.
triggers: ["pwa not working ios", "safari service worker issue", "ios pwa storage cleared", "push notifications ios safari", "pwa works android not iphone"]
permissions: ["READ"]
---

## Symptom
A PWA feature that works correctly on Android and desktop Chrome/Edge
fails, behaves inconsistently, or is entirely unavailable specifically on
iOS Safari (including when installed to the home screen) -- storage
being wiped unexpectedly, push notifications not working, or install
behavior differing from other platforms.

## Likely causes
1. **iOS's storage eviction policy for Safari (including installed
   PWAs, historically)** can clear IndexedDB/Cache Storage/localStorage
   after a period of inactivity or under storage pressure, more
   aggressively than desktop browsers -- code that assumes offline-cached
   data persists indefinitely can silently lose it.
2. **No native install prompt (`beforeinstallprompt`) support on iOS
   Safari** -- iOS requires the user to manually use the Share sheet's
   "Add to Home Screen," so any app relying solely on the standard
   `beforeinstallprompt`-triggered install flow has no equivalent path on
   iOS and needs separate, explicit instructions for iOS users.
3. **Web Push support on iOS Safari has specific version/context
   requirements** (historically requiring the app to be installed to the
   home screen first, with support only in newer iOS/Safari versions) --
   code written assuming push works identically to Android/desktop
   Chrome will silently fail to register on older iOS versions or when
   the app isn't installed.
4. **Background sync and some other service worker APIs have limited or
   no support on Safari**, so a feature relying on
   `BackgroundSyncManager` or similar APIs needs a fallback path rather
   than assuming universal support.
5. **Viewport/safe-area and standalone-display-mode quirks specific to
   iOS** (notch/home-indicator safe areas, status bar styling) that don't
   have a direct equivalent on other platforms and need iOS-specific CSS
   (`env(safe-area-inset-*)`) to handle correctly.

## Diagnose
- Reproduce the specific failure on an actual iOS device/Safari (or
  Safari's remote debugging via a connected Mac) rather than assuming
  desktop Safari or a simulator's behavior is fully representative --
  version-specific PWA capability differences are common enough that
  testing the actual target iOS version matters.
- Check whether the failing feature depends on an API with known Safari
  support gaps (background sync, certain push notification
  requirements) via a compatibility reference, before assuming it's an
  app-specific bug.
- For storage-loss reports, check whether the affected users had the app
  installed to the home screen (generally more storage-durable) versus
  used purely as a Safari tab, and how long since their last visit before
  data loss was noticed.

## Fix
- Design any offline-cached data as recoverable/re-fetchable rather than
  as the sole source of truth -- treat client-side storage on iOS as a
  performance/offline optimization, not guaranteed durable storage, and
  re-sync from the server when data is found to be missing rather than
  treating its absence as an error state.
- Provide explicit, iOS-specific "Add to Home Screen" instructions
  (detecting iOS Safari specifically) since the standard install-prompt
  UX doesn't apply there.
- Feature-detect push notification and background sync support at
  runtime and provide a graceful fallback (e.g. in-app notification
  center, foreground polling) rather than assuming universal
  availability -- don't gate core functionality on APIs with partial
  platform support.
- Use `env(safe-area-inset-*)` CSS environment variables to handle
  notch/home-indicator safe areas correctly in standalone display mode,
  tested specifically on iOS devices with those physical features.

## Pitfalls
- Assuming iOS PWA support has stayed static -- Apple has changed PWA/
  Safari capabilities across iOS versions historically (including web
  push availability), so a compatibility assumption baked in at one point
  can become outdated; re-verify against the current target iOS versions
  rather than relying on old notes indefinitely.
- Building an entire feature's architecture around an API with iOS-partial
  support (e.g. relying on background sync as the only mechanism for a
  core feature) creates a permanently degraded experience for a
  significant user segment rather than a graceful, intentional fallback.

## Verify
Test the specific previously-broken feature on the actual target iOS
version(s), both as a plain Safari tab and installed to the home screen,
and confirm either full functionality or a clearly-designed, working
fallback -- not a silent failure.
