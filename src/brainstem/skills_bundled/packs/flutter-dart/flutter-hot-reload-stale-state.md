---
name: flutter-hot-reload-stale-state
description: Diagnose a code change that hot reload doesn't reflect because it actually requires a hot restart.
triggers: ["hot reload not working flutter", "change not showing up after hot reload", "flutter hot reload doesnt update", "initstate change not applying"]
permissions: ["READ"]
---

## Symptom
A code change -- inside `main()`, a `const` field's initial value, an
enum, native plugin code, or a `State`'s `initState()` -- doesn't appear
after hot reload, leading the developer to assume the change is buggy or
wasn't applied, when actually a hot restart or full rebuild was required.

## Likely causes
1. **The change is to code that only runs once at startup** -- `main()`
   itself, or top-level/static/const initializers -- which hot reload
   doesn't re-execute; only a hot restart re-runs `main()`.
2. **The change modifies a `State`'s `initState()` logic or field
   initializers**, but hot reload preserves already-mounted State
   objects, so `initState()` doesn't run again for them.
3. **The change is to native/platform code** (Android Kotlin/Java, iOS
   Swift/Obj-C), plugin registration, `pubspec.yaml` dependencies, or
   newly added assets -- none of which the Dart-only hot reload mechanism
   picks up.
4. **The edit falls into a documented unsupported category** for hot
   reload, such as changing an enum's values or a generic type signature,
   which Flutter explicitly cannot apply via reload and silently no-ops
   instead of erroring clearly.

## Diagnose
- Check the terminal running `flutter run` for a message like "Hot
  reload was rejected" or a suggestion to hot restart -- Flutter often
  does report this, but it's easy to miss when scrolled past.
- Classify the edit: is it inside `main()`, a `const`, `initState`,
  native code, `pubspec.yaml`, or an enum/generic signature? If so, hot
  reload not applying it is expected behavior, not a bug.
- Perform a hot restart (`R` in the terminal, or the IDE's restart
  button) with no other changes and confirm the edit now takes effect --
  this confirms it was a hot-reload-scope issue rather than a real defect
  in the code.

## Fix
- Learn which categories of edits require a restart versus a reload, and
  default to hot-restarting after touching `main()`, top-level state,
  `initState`, native code, dependencies, or assets, rather than assuming
  the change is broken.
- When iterating specifically on `initState`/constructor logic, move the
  logic temporarily into a method triggered by a rebuild-safe action
  (e.g. a button press) during development, then move it back once
  verified, to shorten the iteration loop.
- For native/platform channel changes, fully stop and re-run
  `flutter run` rather than just hot restarting, since some native build
  artifacts require a fresh build step.

## Pitfalls
- Concluding the *feature itself* is broken after a change silently
  didn't apply via hot reload wastes debugging time chasing a phantom
  bug -- always rule out "did this need a restart" first, especially for
  `initState`/constructor edits.
- Habitually hot-restarting after every single change (instead of
  learning which edits are reload-safe) defeats the fast-iteration
  benefit hot reload exists for -- reserve restart for the categories
  above and reload for ordinary build()/method-body changes.

## Verify
After hot-restarting (not reloading), confirm the change takes effect
exactly as expected; then make an unrelated, reload-safe change (e.g. a
widget's build() text or style) and confirm hot reload alone reflects
it, establishing the tool is working normally and the earlier issue was
scope, not breakage.
