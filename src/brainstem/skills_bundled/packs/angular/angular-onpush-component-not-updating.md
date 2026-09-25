---
name: angular-onpush-component-not-updating
description: Diagnose an OnPush component that fails to visually update even though the bound data has confirmably changed.
triggers: ["onpush not updating", "component not rerendering angular", "changedetectionstrategy onpush not working", "view not updating after data change angular"]
permissions: ["READ"]
---

## Symptom
A component declared with `changeDetection: ChangeDetectionStrategy.OnPush`
doesn't visually update in the browser even though a `console.log` or the
Redux/store DevTools confirm the underlying data actually changed --
often described as "the data updated but the screen didn't."

## Likely causes
1. **In-place mutation of an object/array** (`.push()`, `.splice()`, or a
   direct property assignment) passed as an `@Input`, instead of replacing
   the reference -- OnPush only re-checks a component when an `@Input`'s
   *reference* changes, so mutation is invisible to it.
2. **The update happens outside Angular's zone** -- a callback from a
   non-patched library, a Web Worker `message` handler, or code run inside
   `ngZone.runOutsideAngular` -- so zone.js never schedules change
   detection for that update at all, OnPush or not.
3. **The template binds a plain field updated from a manual `.subscribe()`
   callback**, not the `async` pipe or a signal, so nothing tells the
   OnPush component it needs to be checked on the next cycle.
4. **A necessary `markForCheck()` was omitted** after a state update that
   happens outside the normal input/event/async-pipe paths OnPush already
   tracks automatically.

## Diagnose
- Record an interaction in Angular DevTools' Profiler; if the component's
  bar never appears in the frame where the data changed, change detection
  wasn't triggered at all for it -- a zone/scheduling issue, not a
  rendering-logic issue.
- Add a log inside `ngOnChanges`: if the component is `@Input`-driven, a
  genuine reference change should log a new value; if it doesn't fire
  despite the source object being logged as "changed" elsewhere, compare
  old and new references with `Object.is()` to confirm a mutation, not a
  reassignment, occurred.
- Grep the code path that performs the update for `.push(`, `.splice(`,
  `.sort(`, or direct property assignment on the object/array passed in
  as this component's `@Input`.
- Log `ngZone.isInAngularZone()` inside the callback that performs the
  update to check whether it's even running inside the zone.

## Fix
- Replace in-place mutation with an immutable update (spread the array or
  object into a new reference) at the point the data changes, so OnPush's
  reference-identity check actually notices it.
- For updates that genuinely originate outside the zone, either wrap the
  state update in `ngZone.run(() => ...)` so it re-enters Angular's zone,
  or call `changeDetectorRef.markForCheck()` explicitly right after the
  internal state changes to flag the component dirty for the next cycle.
- Prefer the `async` pipe (or a signal produced via `toSignal()`) for
  observable-derived template values under OnPush -- both call
  `markForCheck()` internally on each emission, removing the need to
  manage change detection by hand.

## Pitfalls
- Sprinkling `changeDetectorRef.detectChanges()` everywhere to make OnPush
  "just work" defeats the point of OnPush (skipping unnecessary checks)
  and can trigger `ExpressionChangedAfterItHasBeenCheckedError` if called
  mid-cycle -- `markForCheck()` (schedule for next cycle), not
  `detectChanges()` (force immediately), is almost always the right call.
- Switching to immutable updates for the outer array while still mutating
  a nested object inside it in place still fails wherever that nested
  object is passed as its own `@Input` to an `*ngFor` row component under
  OnPush -- immutability has to hold at every level actually bound.

## Verify
With the Angular DevTools Profiler recording, trigger the same data
change again and confirm the OnPush component's bar now appears in that
cycle, and the DOM reflects the new value without requiring a manual page
reload or an unrelated interaction to force a stray re-render.
