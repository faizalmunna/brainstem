---
name: combobox-aria-role-misuse
description: Fix a custom dropdown or autocomplete that a screen reader announces incorrectly or not at all due to missing or wrong ARIA combobox roles.
triggers: ["screen reader doesn't announce dropdown", "custom select not accessible", "combobox aria role", "autocomplete not announced by nvda", "screen reader says nothing when i open dropdown"]
permissions: ["READ"]
---

## Symptom
A custom-built dropdown or autocomplete (a `div`-and-`ul` widget styled to
replace a native `<select>`) works fine visually and with a mouse, but a
screen reader user either hears nothing when they open it, hears it
announced as a plain list or generic group with no indication it's a
selectable control, doesn't get told which option is currently
highlighted while arrowing through options, or has focus visually move
between options but the screen reader keeps re-announcing the same
option or none at all.

## Likely causes
1. **No ARIA role at all, or the wrong one** -- a `div` with `onClick`
   handlers and CSS styling has no implicit role, so it's exposed as a
   generic, non-interactive node; screen readers have nothing to
   identify it as a form control.
2. **`role="combobox"` applied without the required relationship
   attributes** -- the WAI-ARIA combobox pattern requires `aria-
   expanded`, `aria-controls` (pointing to the listbox's id),
   `aria-activedescendant` (pointing to the currently highlighted
   option's id), and the listbox itself needs `role="listbox"` with
   children as `role="option"`. Missing any one of these breaks the
   announcement even if the role name is right.
3. **DOM focus is moved to each option as the user arrows through
   it**, instead of keeping real focus on the input/combobox and using
   `aria-activedescendant` to indicate the "virtual" active option --
   moving real focus fires multiple focus/blur events that confuses
   screen reader state tracking and can drop keystrokes.
4. **The popup listbox is conditionally removed from the DOM** (not
   just visually hidden) on close and re-inserted on open, so
   `aria-controls` sometimes points at an id that doesn't exist yet,
   and screen readers cache stale relationship info from the previous
   render.

## Diagnose
- Inspect the combobox trigger element in devtools: confirm it has
  `role="combobox"`, `aria-expanded`, and `aria-controls` referencing an
  id that actually exists in the DOM at that moment.
- Turn on a screen reader (NVDA + Firefox, or VoiceOver + Safari) and
  open the widget: it should announce something like "combobox, collapsed"
  then "expanded" on open, and each arrow-key move should announce the
  option text plus its position (e.g. "Option 3 of 8").
- Check whether focus (via `document.activeElement` in devtools) actually
  moves per option, or stays on the combobox input while
  `aria-activedescendant` changes -- the pattern requires the latter.
- Run axe DevTools; it flags `aria-controls` referencing a non-existent
  id and missing required combobox attributes, though it can't catch
  live announcement behavior -- manual screen reader testing is still
  required for that.

## Fix
Implement the full WAI-ARIA Combobox Pattern as a single coherent
contract, not a role name bolted onto existing markup: the text input or
button keeps `role="combobox"` and real DOM focus at all times; `aria-
expanded` toggles with the popup's open state; `aria-controls` points at
the popup's id; the popup has `role="listbox"` and its children `role=
"option"` with stable ids; and as the user moves the highlighted option
with arrow keys, only `aria-activedescendant` on the combobox changes
to that option's id -- real focus never leaves the input. This lets the
screen reader announce option changes as if focus moved, without the
side effects of actually moving it. Where possible, use a tested
implementation (Downshift, react-aria's `useComboBox`, Radix's
`Combobox`) instead of hand-assembling these attributes, because the
interaction between `aria-activedescendant` timing and DOM mutation
order is easy to get subtly wrong.

## Pitfalls
- Adding `role="combobox"` to satisfy an automated scanner without also
  wiring `aria-activedescendant` "fixes" the audit but not the actual
  experience -- screen reader users still won't hear which option is
  highlighted while navigating.
- Using `aria-live="polite"` on the listbox to announce the highlighted
  option as a workaround for missing `aria-activedescendant` causes
  double or delayed announcements and doesn't communicate the same
  semantic relationship -- it's a symptom patch, not the pattern.
- Removing and re-mounting the popup listbox on every open/close (rather
  than toggling visibility) can momentarily leave `aria-controls`
  pointing at a nonexistent id during the render, which some screen
  readers latch onto incorrectly.

## Verify
With NVDA or VoiceOver running, open the combobox and confirm it
announces "combobox" plus expanded/collapsed state, then arrow through
options and confirm each one is announced by name and position without
moving real DOM focus away from the input (verify via devtools that
`document.activeElement` stays the combobox throughout).
