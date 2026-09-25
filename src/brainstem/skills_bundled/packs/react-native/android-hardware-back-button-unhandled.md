---
name: android-hardware-back-button-unhandled
description: Fix the Android hardware or gesture back button exiting the app or skipping a screen instead of navigating back as expected.
triggers: ["back button closes app instead of going back", "android back button skips screen", "hardware back button not working react native", "back gesture exits app unexpectedly", "backhandler not intercepting back press"]
permissions: ["READ"]
---

## Symptom
Pressing Android's hardware/gesture back button exits the app entirely
(or jumps back two screens instead of one, or closes a modal *and* the
screen behind it) when the expected behavior is to go back one logical
step -- a bug class that has no iOS equivalent, since iOS has no system-
wide back button, which is often why it's missed in development done
primarily on iOS.

## Likely causes
1. **No `BackHandler` listener registered for a screen with custom
   back behavior** -- a screen showing a modal, a multi-step wizard, or a
   WebView expects back to step within itself first, but without a
   registered `BackHandler.addEventListener('hardwareBackPress', ...)`
   handler, Android's default behavior (pop the navigation stack, or
   exit if already at the root) applies instead.
2. **A registered `BackHandler` listener that never returns `true`** --
   the handler function runs but returns `false`/`undefined`, which tells
   the system "this event wasn't handled, keep bubbling," so the default
   pop/exit behavior still happens *in addition to* whatever the handler
   did, producing a double-navigation (e.g. closing a modal AND popping
   the screen behind it in the same back press).
3. **Multiple `BackHandler` listeners registered across mounted
   screens/modals with no coordination** -- if several are active
   simultaneously (e.g. a screen's own listener plus a modal's listener
   both still registered), the return-value/priority ordering may not
   match visual stacking order, so back affects the wrong layer.
4. **A listener registered but never removed on unmount**, so a
   previous screen's stale `BackHandler` handler keeps intercepting back
   presses on a new screen, making it seem like the current screen's back
   handling "doesn't work" when actually a leftover handler from a
   different screen is consuming the event first.
5. **Being at the root of the navigation stack with no explicit
   "confirm exit" handling**, where the reported bug is actually "the app
   exits with no confirmation," a legitimate UX gap rather than a broken
   handler -- distinct from cases 1-4 where handling exists but is wrong.

## Diagnose
- Reproduce with a physical back-button press (or the emulator's back
  button / 3-button nav back, and separately the gesture-nav back
  swipe, since some devices handle these through slightly different
  paths) rather than only testing via a software "back" UI element,
  which doesn't exercise `BackHandler` at all.
- Grep for `BackHandler.addEventListener` across the codebase and check,
  for each, whether the handler function explicitly `return true` on the
  branch that handles the press, and whether there's a matching `.remove()`
  in a cleanup function.
- Add a log at the top of every registered handler (temporarily) to see,
  on a single back press, which handler(s) actually fire and in what
  order -- this reveals stale/duplicate listeners immediately.
- For modal-over-screen cases specifically, check whether the modal's own
  handler is registered/unregistered exactly in sync with the modal's
  visibility, not just once on the parent screen's mount.

## Fix
- Register a `BackHandler` listener scoped to exactly the lifetime it
  should apply to (inside a `useFocusEffect`/`useEffect` tied to the
  screen or modal's mounted/focused state), and explicitly `return true`
  whenever the handler consumes the press (closing a modal, stepping a
  wizard back), `return false` only when it should fall through to
  default navigation behavior.
- For screens with several layered dismissible things (a modal over a
  screen over a stack), give each its own listener registered only while
  visible, relying on React Navigation's/RN's registration order (most
  recently registered handles first) rather than trying to manually
  coordinate priority across unrelated components.
- Always pair `addEventListener` with `removeEventListener`/the
  subscription's `.remove()` in cleanup, matched to the same
  mount/visibility lifecycle as the registration, to avoid stale handlers
  intercepting presses meant for a different screen.
- If the "exit app" behavior at the root is intentional but needs a
  confirmation step, add an explicit double-back-to-exit or a confirm
  dialog handler at the root, rather than leaving default immediate-exit
  behavior unaddressed and calling it a UX bug later.

## Pitfalls
- Registering a `BackHandler` listener but forgetting to return `true`
  is the single most common mistake here -- it looks like the handler
  "isn't running" (because the default action masks whatever the handler
  did), when it actually ran and just failed to signal that it consumed
  the event.
- Testing back-button fixes only via `adb shell input keyevent 4` in
  scripted testing without also testing the real gesture-nav back swipe
  on Android 10+ devices can miss cases where gesture navigation
  interacts differently with certain edge-swipe-sensitive components
  (like `react-native-screens`' native stack transitions).

## Verify
On a physical Android device (or emulator) with both 3-button and
gesture navigation modes tested separately, press back through the
full expected flow (closing a modal, stepping a wizard, popping a
screen, and finally exiting from the root with any intended
confirmation) and confirm each press produces exactly one logical step
of back-navigation, never a skipped screen or an immediate unintended
exit.
