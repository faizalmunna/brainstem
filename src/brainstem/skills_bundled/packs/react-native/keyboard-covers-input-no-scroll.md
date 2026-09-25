---
name: keyboard-covers-input-no-scroll
description: Fix an on-screen keyboard that covers a focused text input with no automatic scroll or view adjustment to keep it visible.
triggers: ["keyboard covers input", "keyboard hides text field", "keyboardavoidingview not working", "text input hidden behind keyboard", "can't see what i'm typing on keyboard open"]
permissions: ["READ"]
---

## Symptom
Tapping a `TextInput` near the bottom of the screen (or any input in a
form with several fields) brings up the keyboard, which covers the input
entirely -- the user can't see what they're typing, and nothing
scrolls or resizes to compensate, even though the same screen may work
fine on the other platform.

## Likely causes
1. **No `KeyboardAvoidingView` (or a misconfigured one) wrapping the
   screen** -- without it, neither iOS nor Android automatically resizes
   or repositions the RN view hierarchy when the keyboard appears.
2. **Wrong `behavior` prop for the platform** -- `KeyboardAvoidingView`
   needs `behavior="padding"` on iOS but typically `"height"` or no
   behavior (relying on `android:windowSoftInputMode`) on Android;
   using iOS's behavior value unconditionally on Android (or vice versa)
   produces no effect or a broken layout.
3. **Missing/incorrect `android:windowSoftInputMode` in
   `AndroidManifest.xml`** -- Android's own resize-on-keyboard behavior
   is controlled at the native Activity level (`adjustResize` vs
   `adjustPan` vs `adjustNothing`); the default or a wrong value means no
   amount of JS-level `KeyboardAvoidingView` configuration will help.
4. **A `KeyboardAvoidingView` present but not sized/positioned to cover
   the actual scrollable content** -- e.g. it wraps only part of the
   screen, has no `flex: 1`, or a fixed `keyboardVerticalOffset` that
   doesn't account for a header/tab bar, so it technically "works" but by
   an amount that still leaves the input covered.
5. **The input is inside a `ScrollView`/`FlatList` with no way to scroll
   to the focused field** -- avoiding the keyboard requires knowing which
   input is focused and scrolling it into view, which plain
   `KeyboardAvoidingView` doesn't do for content taller than the screen.

## Diagnose
- Reproduce on both platforms and note whether the issue is iOS-only,
  Android-only, or both -- the fix differs significantly by platform.
- Check whether `KeyboardAvoidingView` is present in the component tree
  at all, and if so, what `behavior` prop it's using and whether that
  wrapper actually contains the affected input (not a sibling).
- For Android, check `android:windowSoftInputMode` in
  `android/app/src/main/AndroidManifest.xml` for the relevant `<activity>`
  -- if it's `adjustPan` or unset/`adjustUnspecified`, the OS won't resize
  the window to make room.
- For a scrollable form, check whether tapping a *lower* input scrolls it
  above the keyboard automatically, or whether only the topmost input(s)
  are reachable -- indicates missing "scroll to focused input" logic
  rather than a missing `KeyboardAvoidingView` entirely.

## Fix
- Wrap the screen's content in `KeyboardAvoidingView` with `flex: 1`, and
  set `behavior={Platform.OS === 'ios' ? 'padding' : 'height'}` (or
  `undefined` on Android if manifest-level resizing already handles it --
  test both to avoid double-compensation).
- Set `android:windowSoftInputMode="adjustResize"` on the activity in
  `AndroidManifest.xml` so Android's own window manager shrinks the
  content area when the keyboard appears, which is often the actual fix
  needed on Android rather than anything in JS.
- For forms taller than the screen, use a library built for this
  (`react-native-keyboard-aware-scroll-view`'s
  `KeyboardAwareScrollView`, or `KeyboardAvoidingView` combined with
  manually calling `scrollResponderScrollNativeHandleToKeyboard` /
  `ref.current.scrollToFocusedInput`) so the specific focused field
  scrolls into view above the keyboard, not just the whole view shifting
  by a fixed amount.
- Account for any fixed header/tab bar height in
  `keyboardVerticalOffset` on iOS, since `KeyboardAvoidingView` measures
  from its own position, not the screen top.

## Pitfalls
- Setting `adjustResize` on Android while also wrapping in
  `KeyboardAvoidingView` with a non-zero `behavior` can double-compensate,
  shrinking the layout twice and leaving excessive blank space above the
  keyboard -- pick one mechanism per platform and verify there isn't a
  second one also active.
- Hardcoding a `keyboardVerticalOffset` pixel value tuned for one device
  breaks on devices with different header heights, notches, or dynamic
  type sizes -- derive the offset from actual measured header height
  (e.g. `useSafeAreaInsets` plus a measured header ref) instead of a
  magic number.

## Verify
On both a physical iOS device and a physical Android device (simulators
can behave differently for keyboard timing), focus each input in the
form -- including the last/lowest one -- and confirm the input remains
fully visible above the keyboard with no manual scrolling required, and
that dismissing the keyboard returns the layout to its original state.
