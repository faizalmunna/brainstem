---
name: flutter-release-build-crash-obfuscation
description: Diagnose an app crashing only in release or profile builds due to obfuscation or tree-shaking removing needed code.
triggers: ["crashes only in release mode flutter", "works in debug but crashes in release", "obfuscation breaks flutter app", "release build tree shaking crash"]
permissions: ["READ"]
---

## Symptom
The app works correctly in debug and profile builds but crashes, silently
fails a specific feature, or behaves incorrectly only in a release build
(`flutter build apk --release`/`--obfuscate`, or an App Store/Play Store
build), often producing a generic native crash log instead of a helpful
Dart stack trace.

## Likely causes
1. **Code relies on runtime reflection or type-name string matching**
   (e.g. comparing `object.runtimeType.toString()` to a literal, or a
   serialization approach that inspects class/field names reflectively),
   which breaks under `--obfuscate` since class and member names are
   renamed in release builds.
2. **Aggressive release-mode tree-shaking removes code only reachable via
   reflection or a string-keyed dynamic lookup** (e.g. a plugin
   registered only through a string-keyed factory map, or a class only
   ever instantiated via a `Type` lookup) that the compiler can't
   statically prove is used.
3. **An `assert()` statement carries an important side effect**, not just
   a check -- asserts are stripped entirely in release/profile builds, so
   behavior that "worked" in debug silently disappears.
4. **Environment-dependent code paths** (`kDebugMode`/`kReleaseMode`
   branches, or a different API base URL/config per build mode) that
   were never actually exercised until the release build, surfacing a
   genuine but previously-untested path.
5. **Missing Android ProGuard/R8 `-keep` rules for a plugin's classes**
   accessed via native-side reflection, causing minification to strip or
   rename classes the plugin looks up by string name.

## Diagnose
- Build with `flutter build apk --release --split-debug-info=<dir>` and
  use `flutter symbolize` against the crash's obfuscated stack trace to
  recover real method and class names.
- Search the codebase for `runtimeType`, `.toString()` on a `Type`, or
  any string-based class-name comparison/lookup -- these are the classic
  obfuscation casualties.
- Check `assert()` statements for anything beyond a pure boolean
  check -- an assert that also mutates state or calls a function with
  side effects vanishes in release/profile.
- On Android, check `android/app/proguard-rules.pro` for missing `-keep`
  rules for plugin classes, and compare release vs. debug `adb logcat`
  output for `ClassNotFoundException`/`NoSuchMethodError` that only
  appears in the release build.

## Fix
- Replace reflection/string-based type matching with explicit,
  statically-analyzable code (a sealed class hierarchy with a
  switch/`when`, or explicit `fromJson` factories registered in a
  compile-time map) so obfuscation and tree-shaking can't remove or
  rename something referenced only by string.
- Add explicit `-keep` ProGuard/R8 rules (or the iOS equivalent) for any
  classes accessed by name from native/reflective code, so release
  minification doesn't strip or rename them.
- Move side effects out of `assert()` entirely -- asserts should be pure
  validation; do the actual work in normal code so it runs identically
  across build modes.
- Add a release-mode smoke-test pass (or automated integration tests run
  against a `--release` build) covering code paths gated by
  `kReleaseMode`/environment config, since those are otherwise untested
  until users hit them.

## Pitfalls
- Disabling obfuscation/tree-shaking altogether to make the crash go away
  gives up real size and reverse-engineering-resistance benefits release
  builds are meant to provide -- fix the underlying reflection dependency
  instead of turning off the optimization.
- Adding an overly broad `-keep class **` rule to silence a crash defeats
  most of R8's size and obfuscation benefit for the whole app -- scope
  `-keep` rules narrowly to the specific classes or packages that
  actually need protecting.

## Verify
Build the exact release configuration used for the crash
(`flutter build apk --release --obfuscate --split-debug-info=...`, or the
iOS release archive), reproduce the original steps on a real device, and
confirm the crash/incorrect behavior is gone, the symbolized stack trace
still resolves to real names if it were to fail again, and obfuscation
size reduction is still intact rather than accidentally disabled as part
of the fix.
