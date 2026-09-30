---
name: angular-zonejs-third-party-change-detection
description: Diagnose excessive change-detection cycles triggered by a third-party library's callbacks running inside Angular's zone.
triggers: ["too many change detection cycles angular", "third party library causing rerenders", "zone.js performance issue", "chart library triggers change detection angular"]
permissions: ["READ"]
---

## Symptom
A full change-detection cycle (visible as repeated `ApplicationRef.tick()`
entries in a Performance profile, or noticeable CPU spikes) runs far more
often than any Angular-triggered event explains -- typically traced to a
third-party library's internal callback, such as a chart's animation
frame, a maps SDK's drag handler, or a WebSocket client's message handler.

## Likely causes
1. **The library uses `setTimeout`/`setInterval`/`addEventListener`/
   native `Promise`/`XMLHttpRequest` internally**, all of which zone.js
   monkey-patches by default -- every one of those callbacks re-enters
   the Angular zone and triggers `ApplicationRef.tick()`, whether or not
   anything Angular-relevant actually changed.
2. **A high-frequency callback runs inside the Angular zone** (mouse-move
   during a drag, an animation loop, a streaming WebSocket firing many
   small messages per second), and each invocation independently
   schedules a full change-detection pass across the whole component
   tree, not just the one widget that needs updating.
3. **The library's internal state changes don't need Angular to know
   about them at all** (e.g. a canvas redraw), but because the library
   was initialized from code running inside the zone, all of its
   callbacks inherit zone-patching by default.

## Diagnose
- Record a Performance profile while interacting with the third-party
  widget and look for repeated `ApplicationRef.tick`/`zone.run` entries
  whose call stack bottoms out in the library's code rather than
  application code -- confirms the library, not app logic, is the
  trigger.
- Log `NgZone.isInAngularZone()` inside the suspect callback (or set a
  breakpoint) to confirm it's executing inside the Angular zone.
- Count change-detection cycles over a fixed window (a counter incremented
  in a top-level component's `ngDoCheck`) with the widget idle versus
  actively firing its callbacks, to quantify the extra cycles it causes.

## Fix
- Wrap the third-party library's initialization -- or just the specific
  callbacks known to fire often and not need Angular -- in
  `ngZone.runOutsideAngular(() => { ... })`, so those callbacks execute
  outside the zone and stop triggering `ApplicationRef.tick()` entirely.
- Inside a `runOutsideAngular` block, explicitly call
  `ngZone.run(() => ...)` around only the specific state updates that do
  need to reach Angular-bound template bindings (e.g. updating a bound
  "selected point" value after a chart click), so only that subset
  re-enters the zone.
- For components that never need zone-driven change detection at all
  (fully self-managed by a library, or already using OnPush plus signals
  throughout), pair `ChangeDetectionStrategy.OnPush` with manual
  `markForCheck()` calls at the few points that matter, minimizing
  reliance on zone-triggered ticks entirely.

## Pitfalls
- Wrapping the *entire* widget lifecycle in `runOutsideAngular`, including
  the one callback that updates a template-bound value, silently breaks
  that binding -- the DOM won't update until some unrelated event happens
  to trigger CD elsewhere; always re-enter with `ngZone.run()` for the
  specific update that must reach the template.
- Applying this optimization before profiling confirms this specific
  widget is actually causing excess cycles adds real complexity (manual
  zone management is easy to get subtly wrong) for no measured benefit --
  profile first, per the Diagnose section.

## Verify
Re-record the Performance profile doing the same interaction as before;
confirm `ApplicationRef.tick()` no longer fires on every internal library
callback, while the one specific update that should reach the template
(e.g. the click-to-select value) still visibly updates in the DOM.
