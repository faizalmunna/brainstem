---
name: form-error-not-announced-to-screen-reader
description: Fix a form validation error that appears visually but is never announced to screen reader users after they submit.
triggers: ["screen reader doesn't announce form error", "validation error not read aloud", "form error message not accessible", "aria-invalid not announced", "screen reader silent after submit fails"]
permissions: ["READ"]
---

## Symptom
A form shows a red error message under an invalid field after a failed
submit attempt (sighted users see it immediately), but a screen reader
user who submits the same form hears nothing change -- no announcement
of an error, no indication which field is invalid, and focus may still
be sitting on the submit button with no cue that anything went wrong.
They may only discover the problem by manually re-reading every field.

## Likely causes
1. **The error message is inserted into the DOM with no `aria-live`
   region and no focus movement** -- it's a plain `<span>` or `<div>`
   that appears visually via CSS, but since nothing changed focus or is
   marked as a live region, assistive tech has no signal to announce
   anything.
2. **The invalid input isn't marked with `aria-invalid="true"` or
   associated with its error text via `aria-describedby`** -- even if a
   screen reader user tabs to the field, they hear the label and type
   but not that it's currently invalid or why.
3. **Focus stays on the submit button (or wherever it was) after a
   failed submit** instead of moving to a summary of errors or the first
   invalid field, so a screen reader user has no reason to expect
   anything changed elsewhere on the page.
4. **The error region exists and is marked `aria-live`, but the DOM node
   is replaced (removed and re-created) rather than having its text
   content updated in place** -- some screen readers only pick up live
   region announcements on content mutation within a persistent node,
   not on the region itself being swapped out and back in.

## Diagnose
- Submit the form with NVDA or VoiceOver running and listen for any
  announcement at all -- silence confirms nothing is wired for
  assistive tech even if the error is visually obvious.
- Inspect the invalid input in devtools: does it have `aria-
  invalid="true"` and an `aria-describedby` pointing at the id of the
  visible error text?
- Inspect the error message container: does it have `role="alert"` (or
  a live region container with `aria-live="assertive"`/`"polite"`
  present in the DOM *before* the error text is injected, not created
  fresh at the same time as the text)?
- Check where focus lands after a failed submit by watching the
  devtools "focused element" indicator -- if it's unchanged from before
  submission, no assistive-tech user will be cued to look for new
  content.

## Fix
Wire three things together rather than relying on any single one: mark
each invalid field with `aria-invalid="true"` and `aria-describedby`
referencing its specific error message's id, so a screen reader
announces the problem whenever the user is on or returns to that field;
wrap the error text (or an error summary at the top of the form) in an
element with `role="alert"` (implicit assertive live region) that
already exists in the DOM before submission, updating its `textContent`
rather than remounting the node, so the mutation itself triggers the
announcement; and move focus programmatically after a failed submit --
either to an error summary listing all problems (a common, screen-
reader-friendly pattern for forms with multiple errors) or to the first
invalid field -- so screen reader and keyboard users alike land
somewhere that makes the failure obvious immediately.

## Pitfalls
- Using `aria-live="assertive"` on every field-level error message
  causes each one to interrupt and announce as soon as it appears,
  which becomes overwhelming or contradictory when several fields fail
  at once during a single submit -- prefer a single assertive summary
  region for "form has N errors" and gentler (`polite`) or `aria-
  describedby`-driven per-field detail.
- Moving focus to an error summary but not including field-specific
  error text as focusable links back to each field forces screen reader
  users to then hunt through the form again manually.
- Marking a field `aria-invalid="true"` at initial render (before the
  user has interacted with it at all) causes screen readers to announce
  every untouched field as invalid on first focus, which is both untrue
  and annoying -- only set it after validation actually runs.

## Verify
With a screen reader active, submit the form with at least one invalid
field and confirm an announcement occurs immediately (either the alert
region's text or the field's error via `aria-describedby` when focus
lands there), and confirm keyboard focus visibly moves to the error
summary or first invalid field rather than staying on the submit
button.
