---
name: flutter-keyboard-overflow-textfield
description: Diagnose a bottom overflowed by X pixels error that appears only when a text field gains focus.
triggers: ["bottom overflowed by pixels keyboard", "keyboard covers text field flutter", "layout overflow when keyboard opens", "textfield focus causes overflow"]
permissions: ["READ"]
---

## Symptom
When a `TextField` receives focus and the on-screen keyboard appears, the
console shows "BOTTOM OVERFLOWED BY X PIXELS" and/or content behind the
keyboard gets clipped, pushed oddly, or shows the yellow-striped overflow
indicator at the bottom of the screen -- while the same layout looks fine
before the keyboard appears.

## Likely causes
1. **The Scaffold has `resizeToAvoidBottomInset: false`** explicitly set
   (or a custom layout ignores `MediaQuery.viewInsets.bottom`), so
   content is simply covered or overflows instead of the layout
   reflowing.
2. **A fixed-height `Column`/`Container`** was already at the edge of
   available space before the keyboard appeared, so the keyboard's
   intrusion pushes it over the limit with nowhere to shrink to.
3. **The form content isn't wrapped in a scrollable at all**, so when the
   effective viewport shrinks by the keyboard's height, there's no way to
   scroll the now-hidden fields into view.
4. **Bottom padding/inset is computed once and cached** instead of read
   reactively from `MediaQuery.of(context).viewInsets.bottom` on every
   relevant build, so it doesn't adjust as the keyboard toggles.

## Diagnose
- Check the Scaffold for `resizeToAvoidBottomInset` -- if explicitly
  `false`, that is very likely the direct cause; if unset (default
  `true`), the issue is more likely rigid sizing inside the body.
- Focus the TextField in the running app and inspect the layout at the
  moment of overflow, checking whether the reported widget sits directly
  in the body or inside a fixed-height ancestor.
- Print `MediaQuery.of(context).viewInsets.bottom` in the relevant build
  method before and after focusing the field to confirm it changes as
  expected, and check whether layout code actually uses it.
- Test on both a short and a tall device/simulator, since a layout that
  "just barely" fits on a tall device often only reveals the bug on a
  shorter one where the keyboard consumes proportionally more height.

## Fix
- Leave (or set) `resizeToAvoidBottomInset: true` on the Scaffold (the
  default) so the body's available height correctly shrinks when the
  keyboard appears, and ensure the body's layout responds to that shrink
  gracefully.
- Wrap form content in a scrollable (`SingleChildScrollView`, or
  `ListView` for longer forms) so a shrinking viewport lets the user
  scroll the focused field into view instead of it being clipped or
  overflowing.
- Avoid fixed pixel heights for sections that must coexist with the
  keyboard; use flexible sizing within a scrollable-aware layout so
  sections shrink gracefully rather than overflowing the instant space is
  removed.
- For bottom-anchored input bars, combine `SafeArea` with padding equal
  to `MediaQuery.of(context).viewInsets.bottom`, recomputed on every
  build so it tracks the live keyboard height as it animates open and
  closed.

## Pitfalls
- Setting `resizeToAvoidBottomInset: false` to make the error message go
  away trades a caught overflow error for a silent one -- the field is
  now hidden behind the keyboard with no error at all, which is worse for
  the user even though the console looks clean.
- Wrapping everything in a `SingleChildScrollView` without testing the
  non-keyboard state can introduce an unwanted scroll/visual jump on
  screens that previously didn't need to scroll -- verify the layout
  still looks static and correct with the keyboard dismissed.

## Verify
Focus each TextField on the affected screen (not just the first one) and
confirm no overflow error appears in the console and the focused field
remains visible above the keyboard, on both a short-screen device and
with any predictive-text/suggestion bar enabled that adds extra height.
