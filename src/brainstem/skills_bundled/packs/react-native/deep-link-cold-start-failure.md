---
name: deep-link-cold-start-failure
description: Fix a deep link that opens the correct screen when the app is already running but fails to navigate there on a cold start.
triggers: ["deep link not working on cold start", "universal link opens app but wrong screen", "deep link works when app is open but not closed", "linking getinitialurl not working", "app opens to home screen from notification instead of target screen"]
permissions: ["READ"]
---

## Symptom
Tapping a deep link (a universal link/App Link, or a notification tap
with a link payload) while the app is already running navigates to the
correct screen -- but tapping the same link when the app is fully closed
(cold start) launches the app to its default home screen, ignoring the
link entirely, or briefly flashes the correct screen before snapping back
to home.

## Likely causes
1. **Only `Linking.addEventListener('url', ...)` is handled, not
   `Linking.getInitialURL()`** -- the event listener only fires for links
   received while the JS runtime is already alive; a cold start needs the
   *initial* URL fetched explicitly, since the OS launched the app with
   that URL before any JS event listener could have been registered to
   catch it.
2. **Navigation isn't ready yet when the initial URL resolves** -- on
   cold start, `getInitialURL()` can resolve before the navigator has
   mounted/finished its own initialization, so a `navigate()` call
   fires into a navigator that either doesn't exist yet or immediately
   gets overwritten by the navigator's own `initialRouteName` mounting
   after it.
3. **React Navigation's linking config is incomplete or mismatched** --
   the `linking` prop's path-to-screen mapping doesn't cover the actual
   incoming URL pattern (missing a route, wrong param names, or a
   `screens` config that doesn't nest correctly for a link pointing deep
   into a nested navigator).
4. **A splash-screen or auth/bootstrap flow that unconditionally
   navigates to a default route after its own async setup completes**,
   racing with (and winning against) the deep link's navigation because
   it runs after the deep-linked navigation already happened.
5. **Platform configuration gaps** -- missing/incorrect
   `associatedDomains` entitlement and `apple-app-site-association` file
   for iOS Universal Links, or a missing `intent-filter` with
   `android:autoVerify="true"` plus a missing/incorrect
   `assetlinks.json` for Android App Links -- causing the OS to open a
   browser instead of the app at all, which looks like "the deep link
   doesn't work" but is actually never reaching the app's JS layer.

## Diagnose
- Determine which failure mode this is: does the OS even launch the app
  from the link (app opens to *some* screen) or does it open a browser
  instead? The latter means the native link association (Universal
  Links/App Links config) is broken, not the JS routing.
- Add logging around both `Linking.getInitialURL()` and the
  `'url'` event listener to confirm which one fires (or doesn't) on a
  true cold start (fully force-quit the app first, not just backgrounded).
- Log the exact URL/params React Navigation's `linking.getStateFromPath`
  (or a manual parse) resolves them to, and compare against the actual
  `linking.config` route tree -- a silent mismatch often means the path
  parses to `undefined`/falls through to the default state.
- Check the ordering: log a timestamp when the initial URL resolves and
  when the navigator becomes ready (`onReady` on `NavigationContainer`)
  -- if the URL resolves before `onReady`, a raw `navigate()` call made
  before that point is being dropped or racing another initial
  navigation.
- For Universal Links/App Links specifically, verify the well-known
  association files are actually being served correctly:
  `https://<domain>/.well-known/apple-app-site-association` and
  `.../assetlinks.json` should return valid JSON with the right bundle
  ID/package name and signing hash, not a 404 or an HTML error page.

## Fix
- Use React Navigation's `linking` prop with both `prefixes` and a
  `config` that covers every deep-linkable route, and let
  `NavigationContainer` handle `getInitialURL` internally (it does this
  automatically when `linking` is configured) rather than hand-rolling
  `Linking.getInitialURL()` plus manual `navigate()` calls that can race
  navigator readiness.
- If a custom/manual linking solution is required, gate any initial
  `navigate()` call on `NavigationContainer`'s `onReady` callback (or a
  ref-based "navigator is ready" flag), queuing the pending URL until
  that point instead of firing immediately.
- Make sure any bootstrap/auth flow's own default-route navigation checks
  for a pending deep link first (or defers to the linking config's
  resolved initial state) rather than unconditionally overwriting
  whatever route the deep link resolved to.
- Fix the native association files/entitlements for Universal Links/App
  Links so the OS routes the tap to the app at all -- this is a
  prerequisite that no amount of JS-side linking config can work around.

## Pitfalls
- Testing deep links only via `npx uri-scheme open` or `adb shell am
  start` while the app is already running verifies the warm-start path
  only -- always additionally force-quit the app before testing the
  cold-start path, since that's the specific case most linking bugs hide
  in.
- Fixing the race by adding an arbitrary `setTimeout` before navigating
  "gives the navigator time to mount" in testing but is inherently
  flaky across devices with different startup speeds -- use the actual
  readiness signal (`onReady`, or the `linking` prop's built-in handling)
  instead of a timing guess.

## Verify
Force-quit the app completely, then tap the deep link (or a notification
with a link payload) from outside the app (e.g. via `adb shell am
start -a android.intent.action.VIEW -d "<url>"` or a Notes app link on
iOS) and confirm the app launches directly to the correct target screen
with correct params on the first attempt -- repeat for at least two
different deep-linked routes, not just the one that was being debugged.
