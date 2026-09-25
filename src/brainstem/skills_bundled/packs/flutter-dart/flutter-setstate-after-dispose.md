---
name: flutter-setstate-after-dispose
description: Diagnose a setState-after-dispose error from an async Future resolving after the widget was disposed.
triggers: ["setstate called after dispose", "this widget has been unmounted", "setstate after dispose flutter error", "async callback crashes after navigating away"]
permissions: ["READ"]
---

## Symptom
A red "setState() called after dispose()" error (or "This widget has
been unmounted, so the State no longer has a context") appears in the
console, typically right after the user quickly navigates away from a
screen while an async operation it started -- a network call, timer, or
animation -- is still in flight.

## Likely causes
1. **An awaited Future (API call, database query, file read) resolves
   after the State has already been disposed**, and its completion code
   calls `setState` unconditionally.
2. **A `Timer.periodic` or `Stream` subscription created in `initState`
   is never cancelled in `dispose()`**, so its callback keeps firing and
   calls `setState` on a widget that no longer exists.
3. **A listener on an `AnimationController`/`TextEditingController`**
   added in `initState` keeps invoking a callback that calls `setState`
   after the owning widget is disposed, because it was never removed in
   `dispose()`.
4. **Chained async calls** (`.then().then()`) where only the outer
   Future's cancellation is considered, but an inner one still fires
   `setState` independently after unmount.

## Diagnose
- Read the stack trace in the error -- it names the exact State class and
  the line calling `setState`; open that file first.
- Check whether that call site is inside an awaited Future's continuation
  and whether `dispose()` in the same class does anything to guard
  against firing after unmount (a `mounted` check, cancellation of the
  underlying operation).
- Grep the State class for every Timer/StreamSubscription/
  AnimationController/listener created in `initState`/`build` and verify
  each has a matching cancellation in `dispose()`.
- Reproduce reliably: trigger the async action, then immediately navigate
  back (`Navigator.pop`) before it resolves, in debug mode, to confirm
  the exact trigger path.

## Fix
- Guard every `setState` call that follows an awaited Future with a
  `mounted` check immediately before the call (`if (!mounted) return;`),
  since `mounted` becomes false right after `dispose()` runs.
- For cancellable work, actually cancel it in `dispose()` rather than
  only guarding the callback: cancel Timers (`timer.cancel()`), cancel
  StreamSubscriptions (`subscription.cancel()`), and dispose
  AnimationControllers, so the underlying work stops instead of merely
  being ignored.
- Prefer a state-management pattern (Riverpod's `AsyncNotifier`, Bloc)
  where the async operation lives outside the widget's lifecycle and the
  widget only observes the final state, decoupling disposal from whether
  the async call updates a widget directly.
- For genuinely cancellable long-running work, use `CancelableOperation`
  (`package:async`) so in-flight work actually stops rather than just
  having its side effect suppressed.

## Pitfalls
- Sprinkling `mounted` checks everywhere without also cancelling the
  underlying timer/subscription silences the crash but leaves the
  timer/listener running forever in the background -- a real, just
  quieter, leak.
- Checking `mounted` only at the top of an async function (before the
  `await`) doesn't protect against unmounting that happens *during* the
  await -- the check must happen again immediately after each `await` and
  right before each `setState` call.

## Verify
Reproduce the original repro steps (trigger the async action, then
navigate away immediately) several times in debug mode and confirm the
console shows no setState-after-dispose warning, and that DevTools'
memory view shows the disposed widget's State object is actually
collected rather than retained by a still-running Timer/subscription
closure.
