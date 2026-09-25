---
name: native-module-crash-release-only
description: Debug a native module crash that only reproduces in a release/production build and never happens when running the app in debug mode.
triggers: ["crashes in release but not debug", "release build crashes on launch", "works in debug crashes in release", "native crash only in production build", "app crashes after release build"]
permissions: ["READ"]
---

## Symptom
The app runs fine from Metro in debug mode (`react-native run-ios` /
`run-android`, or a debug APK), but a release build (TestFlight, an
`.aab`/signed APK, or `expo build`/EAS production profile) crashes on
launch or when hitting a specific native module call -- often with no
useful JS stack trace, just a native crash log or an immediate white
screen.

## Likely causes
1. **Hermes bytecode vs. JSC differences exposed only in release** --
   release builds typically enable Hermes/bytecode precompilation and
   stricter optimizations, surfacing subtle JS/native boundary bugs (e.g.
   relying on a global only present under JSC's dev configuration) that
   debug's interpreted mode papered over.
2. **Code stripped by ProGuard/R8 (Android) or dead-code elimination
   (iOS)** -- a native module class, a reflection-based lookup, or a
   native library symbol referenced only indirectly (via `Class.forName`,
   a JS bridge string name, or a dynamically loaded `.so`) gets stripped
   because the obfuscator can't see the reference statically.
2b. **Missing or misconfigured ProGuard keep rules for a native module's
   package**, common with third-party libraries whose bridge registration
   uses reflection.
3. **A debug-only fallback silently masking a real problem** -- code
   guarded by `if (__DEV__)` or `BuildConfig.DEBUG` skips a
   network/permission/config check in debug, so a missing production API
   key, missing entitlement, or missing `google-services.json` config only
   crashes the release path.
4. **Environment/config values baked in at build time differing between
   schemes** -- a release build using a different `.xcconfig`/build
   variant/flavor that points at a different (or missing) native
   configuration file, causing a native module's initializer to crash on
   a null config.
5. **A native module that behaves differently when the JS bundle is
   pre-bundled** (release loads a single `.jsbundle`/`index.android.bundle`
   instead of Metro's live bundle), which changes timing -- a race where a
   native module fires an event before a JS listener has registered,
   masked in debug by Metro's slower initial load.

## Diagnose
- Get the actual native crash log: for iOS, open the `.ips` crash report
  in Xcode's Organizer (Window > Organizer > Crashes) or symbolicate a
  device log; for Android, pull `adb logcat` immediately after the crash
  (`adb logcat -b crash`) or open the crash in Android Studio's App
  Quality Insights / Play Console.
- Search the crash log for the specific native module class name -- if
  the symbol is missing/obfuscated (e.g. a single letter class name with
  no matching mapping), suspect ProGuard/R8 stripping.
- Grep the project for `__DEV__` and `BuildConfig.DEBUG` checks near the
  crashing code path to see if a debug-only branch is hiding a
  precondition.
- Build a release build locally with a debugger attached where possible
  (`react-native run-android --variant=release` with `adb logcat`
  streaming, or a release scheme in Xcode run on a device) instead of
  only testing via TestFlight/Play internal track, to get a live stack
  trace rather than a bare crash report.
- Diff the release build's config files (`Info.plist`, `google-services.json`,
  `.env`/build flavor files) against debug's to spot a missing or
  differently-named key the native module reads at init.

## Fix
- Add explicit ProGuard/R8 `-keep` rules for the native module's package
  and any class it reaches via reflection (check the library's own
  `proguard-rules.pro` if it ships one, and merge it rather than
  reinventing it) so release stripping can't remove code the bridge
  depends on.
- Replace `if (__DEV__)`-guarded shortcuts with real handling in both
  paths -- if a check is safe to skip in debug because a mock config is
  present, make the release path fail loudly with a clear error instead
  of crashing opaquely, or supply the missing production config.
- For Hermes-specific crashes, reproduce with Hermes explicitly enabled
  in a debug build (`hermesEnabled=true` temporarily) to isolate whether
  the bug is Hermes-vs-JSC rather than debug-vs-release build
  configuration.
- For init-order races (native event fires before JS listener attaches),
  buffer the native side's event until a listener is confirmed registered
  (a native module "ready" callback pattern), rather than relying on JS
  bundle load speed to happen to win the race.

## Pitfalls
- Adding an overly broad ProGuard `-keep class ** { *; }` rule "just to
  make the crash go away" defeats stripping for the whole app, bloating
  APK size and hiding future real dead-code issues -- scope keep rules to
  the specific package/class needed.
- Testing the fix only via a debug build with `hermesEnabled` flipped is
  not equivalent to a true release build -- ProGuard/R8 stripping and
  bundle pre-compilation only run in the release build config, so the fix
  must be verified there too.

## Verify
Produce a real signed release build (or a release-variant local build)
and exercise the exact crashing flow on a physical device, confirming via
`adb logcat` (Android) or the device console (iOS) that the previous
crash signature no longer appears and the native module's call completes
normally.
