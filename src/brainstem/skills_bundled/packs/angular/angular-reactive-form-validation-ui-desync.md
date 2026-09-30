---
name: angular-reactive-form-validation-ui-desync
description: Diagnose a reactive form whose displayed validation errors or submit-button state lag behind or disagree with what the user actually typed.
triggers: ["form validation out of sync angular", "submit button state wrong reactive form", "async validator pending state ui", "cross field validation not updating angular"]
permissions: ["READ"]
---

## Symptom
A reactive form displays a field as invalid (or valid) with error text or
styling that doesn't match what the user just typed, or the submit
button's disabled state lags one or more keystrokes behind the visible
input.

## Likely causes
1. **A validator is added or changed with `setValidators()` after the
   `FormControl` already exists, without a following
   `updateValueAndValidity()` call** -- Angular doesn't automatically
   re-run validation just because the validator function reference
   changed.
2. **An async validator (e.g. a username-availability check over HTTP)
   is still pending at submit time** -- the control's status is
   `PENDING`, not yet `VALID`/`INVALID`, and code that only checks
   `form.valid` treats this ambiguously, sometimes allowing submission
   before the check resolves.
3. **Displayed errors are read from a one-time snapshot** (`control.errors`
   captured once in `ngOnInit`) instead of subscribed reactively via
   `statusChanges`, so the view doesn't update when the control's status
   changes later.
4. **A cross-field validator (e.g. "confirm password must match") is
   attached to only one of the two controls**, so changing the *other*
   field in the pair doesn't retrigger validation on the first, leaving
   its error state stuck at whatever it was.

## Diagnose
- Temporarily subscribe to `control.statusChanges` (or `form.statusChanges`)
  and log each emission with a timestamp; compare that timeline against
  when the UI actually updates its error display to see whether the model
  or the view is the one lagging.
- Check the submit handler: does it gate purely on `form.valid`, or does
  it also account for `form.pending` (an async validator still running)?
- For cross-field validators, confirm whether the validator function is
  registered at the `FormGroup` level (correct -- it can see both
  controls) versus on a single child `FormControl` (wrong -- it can't see
  its sibling).
- Search every `setValidators()`/`clearValidators()`/`setAsyncValidators()`
  call site for a following `updateValueAndValidity()` call.

## Fix
- Call `control.updateValueAndValidity()` immediately after
  `setValidators()`/`clearValidators()`/`setAsyncValidators()` so the
  control's status reflects the new rules right away instead of waiting
  for an unrelated value change to trigger it incidentally.
- Move cross-field validation onto the parent `FormGroup`'s validator so
  it has access to both controls and reruns whenever either one changes,
  instead of living on just one child control.
- Gate submit-readiness on `form.status === 'VALID'` explicitly (or
  `!form.invalid && !form.pending`), and disable the submit button while
  `form.pending` is true, so the UI can't get ahead of an in-flight async
  validator.
- Drive displayed error messages from `statusChanges`/`valueChanges` (via
  the `async` pipe or a `toSignal()`-derived signal) instead of a
  one-time snapshot, so the view always reflects current state.

## Pitfalls
- Calling `updateValueAndValidity()` on a parent `FormGroup` from inside
  one of its own validators, without `{ onlySelf: true }`, can trigger an
  infinite validation loop if that same validator's execution is what
  caused the update in the first place -- scope the call correctly or
  restructure to avoid the self-trigger.
- Treating `PENDING` the same as `INVALID` in the UI (showing a red error
  state while an async check is merely in flight) misleads users into
  thinking they made a mistake when the app is just waiting on a network
  call -- show a distinct "checking..." state instead.

## Verify
Type into the field(s) involved, including a case that exercises the
async validator (an already-taken value) and, separately, a cross-field
case (mismatched then corrected values); confirm the error message and
submit-button state update within one validation cycle of each keystroke,
with no stale display left over after the value is corrected.
