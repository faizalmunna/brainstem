---
name: native-event-listener-memory-leak
description: Fix a growing memory leak caused by native event emitter listeners that are never removed when a screen or component unmounts.
triggers: ["native module memory leak", "nativeeventemitter leak warning", "new nativeeventemitter listener added without corresponding remove", "memory grows navigating between screens", "sensor listener not removed"]
permissions: ["READ"]
---

## Symptom
App memory usage climbs steadily as the user navigates in and out of a
particular screen repeatedly (visible in Xcode's Instruments/Memory
graph or Android Studio's Profiler), eventually causing slowdowns or
an OOM crash on lower-memory devices -- often accompanied by a console
warning like "`new NativeEventEmitter()` was called with a non-null
argument without the required `addListener` method" or simply a rising
count of a specific native listener (accelerometer, keyboard, native
push/notification events, a Bluetooth/location SDK's callback).

## Likely causes
1. **A `NativeEventEmitter.addListener` call inside a component with no
   matching `.remove()` in a cleanup function** -- each mount adds another
   subscription to the native side's listener list, and native modules
   generally keep firing to *every* registered listener, including ones
   whose JS-side component has long since unmounted.
2. **Subscribing directly to a native SDK's own listener API (a
   camera/Bluetooth/sensor library's native callback) instead of the
   RN bridge's emitter**, where the library's own removal method
   (often different from RN's generic `.remove()`) is never called,
   because it was overlooked as a "different" kind of subscription.
3. **A shared/singleton listener registered once (e.g. at app root) that
   correctly never unmounts, being confused with a per-screen listener**
   that should have per-mount lifecycle -- the fix applied to the wrong
   one, or a per-screen listener mistakenly treated as a fire-once
   singleton and left unmanaged.
4. **Removing the subscription object incorrectly** -- calling
   `emitter.removeAllListeners(eventName)` from a component that isn't
   the sole owner of that event name removes *other* components' active
   listeners too, while the leaking component's own subscription
   reference was never stored to remove individually.
5. **The native side itself holding a strong reference to a listener
   callback or the emitting object never releasing it**, a genuine native-
   side leak that persists even after the JS side correctly calls
   `.remove()` -- more likely with older or poorly maintained native
   modules that don't implement `removeListeners`/cleanup correctly on
   their end.

## Diagnose
- On iOS, use Xcode's Instruments "Allocations" or "Leaks" template while
  repeatedly mounting/unmounting the screen -- a sawtooth memory graph
  that returns to baseline after each unmount is healthy; a staircase
  that never comes back down points to a leak.
- On Android, use Android Studio's Profiler (Memory tab), force a GC
  (the trash-can icon), and compare heap size before/after several
  mount-unmount cycles of the suspect screen.
- Grep the codebase for `.addListener(` calls against `NativeEventEmitter`
  or `DeviceEventEmitter` and check each one for a corresponding
  `.remove()` (or the older `subscription.remove()` pattern) inside a
  `useEffect` cleanup or `componentWillUnmount`.
- Check the console for RN's own warning about emitter listener count
  ("Possible EventEmitter memory leak detected... N listeners added") --
  it names the event name, which narrows down which subscription is
  accumulating.
- For third-party native SDKs, check their docs specifically for a
  "stop listening"/"unsubscribe" API distinct from the generic RN emitter
  pattern -- don't assume every native listener uses the same removal
  convention.

## Fix
- Store the subscription object returned by `addListener` and call
  `.remove()` on it in the effect's cleanup function (or
  `componentWillUnmount` for class components), mirroring the same
  discipline as removing a JS-level event listener.
- For native SDKs with their own subscribe/unsubscribe API, call that
  SDK's specific teardown method in cleanup rather than assuming RN's
  emitter pattern covers it.
- For shared/global listeners that genuinely should live for the app's
  lifetime, register them once outside per-screen component lifecycles
  (e.g. in a top-level provider that mounts once) so their intentional
  permanence isn't confused with a per-screen leak, and document why they
  aren't removed.
- If a native module's own implementation leaks even after correct JS-
  side removal, update to a newer version that implements proper listener
  cleanup, or wrap the native module's subscribe/unsubscribe behind a
  reference-counted helper so only the last consumer's unmount actually
  tears down the native-side listener.

## Pitfalls
- Calling `emitter.removeAllListeners(eventName)` as a blanket cleanup
  "to be safe" removes listeners other components registered for the
  same event, causing them to silently stop receiving events -- always
  remove the specific subscription instance the component created.
- Adding cleanup that removes the listener on every re-render (not just
  unmount) because the effect's dependency array is wrong causes the
  opposite problem: the listener is added and removed so frequently that
  events get missed between the remove and the next add.

## Verify
Using Instruments (iOS) or the Android Studio Profiler, mount and unmount
the affected screen 10+ times in a row, forcing garbage collection
between cycles where applicable, and confirm memory returns to
approximately the same baseline after each unmount rather than trending
upward -- and confirm the RN "possible EventEmitter memory leak" console
warning no longer appears for that event name.
