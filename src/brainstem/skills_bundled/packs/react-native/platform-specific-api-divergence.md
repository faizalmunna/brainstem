---
name: platform-specific-api-divergence
description: Fix a component or API call that behaves correctly on one platform, iOS or Android, but breaks or looks wrong on the other.
triggers: ["works on ios but not android", "works on android but not ios", "shadow not showing on android", "elevation looks wrong on ios", "platform specific bug react native"]
permissions: ["READ"]
---

## Symptom
A feature that visibly works correctly on iOS renders wrong, throws, or
silently no-ops on Android (or the reverse) -- common examples: a
`shadow*` style shows on iOS but not Android, a `TouchableOpacity`
ripple/feedback looks wrong, a permission prompt never appears on one
platform, or a native API call throws "not supported" only in an Android
or iOS build.

## Likely causes
1. **Style properties that only one platform's renderer implements** --
   `shadowColor`/`shadowOffset`/`shadowOpacity`/`shadowRadius` are iOS-only
   (Android needs `elevation`), while `elevation` has no iOS equivalent;
   assuming one style object covers both platforms produces a shadow-less
   view on whichever platform wasn't targeted.
2. **A JS API or native module method that's genuinely platform-gated**
   (e.g. certain permissions, background task APIs, or haptics
   differ between platforms) called without a `Platform.OS` check or a
   `.ios.js`/`.android.js` file split, so it throws or is a no-op on the
   unsupported platform.
3. **Differing default behavior for the same component** -- e.g.
   `TextInput` autofocus/keyboard behavior, `ScrollView` bounce, or
   `TouchableOpacity` hit-slop defaults differ enough between the two
   platforms' underlying native views that a layout/interaction that
   "just works" on one looks broken on the other without any explicit
   platform-specific code at all.
4. **A third-party native library with incomplete platform support** --
   the JS API surface exists on both platforms but the underlying native
   implementation for one platform is a stub, throws
   `UnsupportedOperationException`/`not implemented`, or was added in a
   later library version than what's installed.
5. **Permission/manifest configuration only done for one platform** -- a
   permission added to `Info.plist` (iOS usage description strings) but
   the corresponding `AndroidManifest.xml` permission, or a runtime
   permission request, was never added (or vice versa).

## Diagnose
- Reproduce on both platforms side by side (simulator/emulator or two
  physical devices) and capture the exact error/log difference -- for a
  crash or thrown error, get the platform-specific stack trace, which
  usually names the exact native class/method that's missing or
  unsupported.
- For style issues, inspect the rendered view in the platform's native
  inspector (Xcode's view debugger for iOS, Layout Inspector in Android
  Studio) to confirm whether the style property was applied at all versus
  applied but rendered differently.
- Check the library's documentation/changelog for a platform support
  matrix -- many RN libraries explicitly list "Android: not supported" or
  "requires iOS 13+" for specific APIs.
- Grep the codebase for `Platform.OS`, `.ios.`, and `.android.` file
  splits near the failing feature to see whether platform branching was
  ever attempted, and whether it's complete on both sides.

## Fix
- Use `Platform.select({ ios: {...}, android: {...} })` (or `.ios.js`/
  `.android.js` file extensions for larger divergences) to give each
  platform the styling/behavior its renderer actually needs -- e.g. both
  `shadow*` properties *and* `elevation` in the same style object so each
  platform picks up its own, rather than trying to find one property that
  covers both.
- Gate platform-unsupported API calls behind `Platform.OS === 'ios'` /
  `'android'` checks with an explicit fallback (a different API, or a
  documented no-op) instead of letting the call throw uncaught on the
  unsupported platform.
- Add the missing manifest/`Info.plist` entry and, for Android 6+/iOS
  runtime permission models, the corresponding runtime permission request
  code -- a declared permission without a runtime prompt (or vice versa)
  fails silently on the platform that requires both.
- When a third-party library's platform support is genuinely incomplete,
  either pin to a version known to support both platforms, find a
  platform-specific alternative for the gap, or wrap the call in a
  capability check so the app degrades gracefully instead of crashing.

## Pitfalls
- Reaching for a cross-platform style hack (e.g. faking Android elevation
  by nesting extra Views with background colors) instead of using
  `elevation` correctly produces visually-close-but-subtly-wrong shadows
  that diverge further on the next Android version's rendering changes.
- Silencing a platform-unsupported API call with an empty catch block
  instead of an explicit `Platform.OS` branch hides the gap from code
  review and from future developers, who won't know the feature is
  intentionally missing on that platform until a user reports it.

## Verify
Run the exact same user flow on both a current iOS simulator/device and a
current Android emulator/device, confirming the feature produces
equivalent (not necessarily pixel-identical, but functionally correct)
behavior on both, and that no platform-specific error appears in either
platform's native log during the flow.
