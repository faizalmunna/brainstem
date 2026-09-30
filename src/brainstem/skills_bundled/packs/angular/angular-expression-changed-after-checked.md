---
name: angular-expression-changed-after-checked
description: Diagnose ExpressionChangedAfterItHasBeenCheckedError thrown in dev mode right after adding a conditional template binding.
triggers: ["ExpressionChangedAfterItHasBeenCheckedError", "expression changed after checked", "ngIf breaks with change detection error", "value changed after it was checked angular"]
permissions: ["READ"]
---

## Symptom
Angular throws `ExpressionChangedAfterItHasBeenCheckedError` in the browser
console (dev mode only) right after adding a conditional binding such as
`*ngIf`, `[ngClass]`, or a plain property binding whose value depends on
something set during a lifecycle hook -- the error names a component and
prints "Previous value" and "Current value" for one specific expression.

## Likely causes
1. **A value read by the template is mutated inside `ngAfterViewInit` or
   `ngAfterContentInit`** -- these hooks run after Angular already checked
   the view once this pass, so the next check within the same detection
   cycle sees a different value than what it just rendered.
2. **A child emits an `@Output` synchronously during its own `ngOnInit`**,
   and the parent's handler updates a property the parent's own template
   already displayed earlier in that same pass.
3. **A getter or method called directly from the template returns a
   different result on consecutive calls** because it derives from
   non-deterministic state (`Date.now()`, `Math.random()`, array `.length`
   after an in-place mutation) rather than a value fixed for the render.
4. **A `BehaviorSubject`-backed service emits synchronously** during
   `ngOnInit`, and the subscribe callback updates template-bound state
   as a side effect of the same change-detection run that's checking it.

## Diagnose
- Read the full error text -- it names the exact component and prints the
  previous and current values, which pinpoints the specific binding
  without guessing.
- Run `ng serve` (a plain dev build, not `--configuration production`) --
  this check only runs in dev mode, so reproduce there, not against a
  prod build where the error is silently skipped.
- Put a breakpoint or `console.trace()` in the setter/getter for the
  flagged property to see the call stack; look for it being set inside
  `ngAfterViewInit`/`ngAfterContentChecked`, or from a child's `@Output`
  handler fired during the child's `ngOnInit`.
- Check the component tree in Angular DevTools for a parent/child pair
  where the child emits a value back to the parent during initialization.

## Fix
- Move logic that mutates ancestor-visible state out of `ngAfterViewInit`/
  `ngAfterContentChecked` into a microtask (`Promise.resolve().then(...)`)
  or `setTimeout(0)`, so the mutation lands in a fresh detection pass
  instead of fighting the one already in progress.
- Restructure child-to-parent data flow so children don't emit values that
  mutate parent state during their own initialization -- pass the final
  value down via `@Input` up front instead of round-tripping it back up
  through an `@Output` during init.
- For values that are legitimately computed asynchronously, initialize
  the bound property with a placeholder that matches the first render,
  then update it from a genuinely async callback (a resolved promise, an
  HTTP response) rather than synchronously inside a hook that runs
  mid-cycle.

## Pitfalls
- Wrapping the mutation in `setTimeout(() => ..., 0)` silences the error
  but introduces a real one-frame visual flash, since the first paint is
  now guaranteed stale -- acceptable only when that flash doesn't matter,
  not as a blanket fix.
- Calling `changeDetectorRef.detectChanges()` inside `ngAfterViewChecked`
  to force a synchronous re-check, without addressing the underlying data
  flow, can spiral into infinite `ngAfterViewChecked` recursion if the
  value keeps changing on every pass.

## Verify
Run the app in dev mode (`ng serve`), exercise the exact interaction path
that triggered the error, and confirm it no longer appears in the console
-- including on the very first render after a full page reload, since
some instances of this bug only appear on initial load, not subsequent
interactions.
