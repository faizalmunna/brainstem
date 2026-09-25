---
name: flutter-platform-channel-platform-specific-crash
description: Diagnose a platform channel call that hangs or crashes only on one platform, Android or iOS.
triggers: ["method channel hangs on ios", "platform channel crash android only", "methodchannel future never completes", "native call works on android but not ios"]
permissions: ["READ"]
---

## Symptom
A `MethodChannel`/`EventChannel` call works fine on one platform (e.g.
Android) but on the other (e.g. iOS) either hangs indefinitely (the
Dart-side `Future` never resolves), throws a `PlatformException`, or
crashes the app outright -- often only reproducible on a physical device
or a release build, not the simulator or debug build.

## Likely causes
1. **The channel or method name string doesn't exactly match** between
   Dart and the platform-specific implementation (a typo, or the iOS
   handler registered under a different channel name than Android's), so
   the call never reaches a handler and the `Future` awaits forever.
2. **The platform handler doesn't call `result.success/error` (or
   `FlutterResult`) on every code path**, especially inside an async
   callback or an error branch, leaving the Dart side hanging.
3. **A main-thread-only native API is called from a background thread**
   (or vice versa) -- iOS UIKit calls off the main thread crash outright,
   while the equivalent Android API may tolerate it, so the same bug only
   surfaces on one platform.
4. **Missing platform-specific permission/entitlement declarations**
   (Info.plist keys, Android manifest permissions) that only fail at
   runtime on the platform enforcing them, producing a native crash
   instead of a catchable Dart exception.
5. **Data sent across the channel isn't a supported codec type** (e.g. a
   Dart `DateTime` or custom object passed directly instead of a
   serializable primitive/map), and one platform's codec is more lenient
   about the mismatch than the other.

## Diagnose
- Reproduce on both platforms with native logging visible:
  `adb logcat` for Android and the Xcode device console (or
  `flutter run -d <ios-device> -v`) for iOS, watching for the native
  handler's own log lines to confirm whether it was reached at all.
- Temporarily wrap the Dart-side call in `.timeout()` during debugging to
  turn a silent hang into an explicit timeout exception with a stack
  trace pointing at the call site.
- Grep both native implementations for the exact channel and method name
  strings and confirm they match the Dart `MethodChannel('exact.name')`
  and invoked method name character-for-character.
- On the crashing platform, check whether the crash log shows a
  "must be called from the main thread" assertion (iOS) or a
  `NetworkOnMainThreadException`/ANR (Android), pointing at a threading
  mismatch.

## Fix
- Define the channel name and every method name as shared constants (or
  keep them in sync with a comment cross-referencing the other file) so
  the string match is exact, and confirm the platform handler is
  actually registered during `configureFlutterEngine`/app startup.
- Guarantee every branch of the native handler calls the result callback
  exactly once, including inside completion handlers and catch blocks --
  a hang almost always traces back to one missing result call.
- Explicitly dispatch main-thread-only work back onto the main thread
  (`DispatchQueue.main.async` on iOS, the main `Handler`/looper on
  Android) before calling APIs that require it, regardless of which
  thread the channel invocation arrived on.
- Restrict channel payloads to primitives and Lists/Maps of primitives
  matching the `StandardMethodCodec`'s supported types, serializing
  custom objects to a `Map` explicitly on both ends.

## Pitfalls
- Wrapping the Dart call in a broad try/catch that swallows the
  `PlatformException` silences the visible crash but hides a real
  native-side bug that resurfaces later as silent data loss or a worse
  crash -- fix the native handler rather than catching around it.
- Leaving a debugging `.timeout()` in production code means the feature
  silently fails after N seconds instead of surfacing why the native side
  never responded -- remove it, or replace it with a real fix, once the
  root cause is found.

## Verify
Trigger the exact same call path on both platforms, ideally on physical
devices since simulators can mask iOS main-thread issues, and confirm
the `Future` resolves with the expected value within normal latency on
both, with no native crash or warning in `adb logcat`/the Xcode console
during the call.
