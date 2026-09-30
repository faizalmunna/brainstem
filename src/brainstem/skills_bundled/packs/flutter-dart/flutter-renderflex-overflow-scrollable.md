---
name: flutter-renderflex-overflow-scrollable
description: Diagnose a RenderFlex overflow error from unconstrained Row or Column widgets inside a scrollable.
triggers: ["renderflex overflowed by pixels", "yellow black overflow flutter", "column overflowed inside listview", "row overflowed on the right"]
permissions: ["READ"]
---

## Symptom
A yellow-and-black striped overflow indicator and a console error like
"A RenderFlex overflowed by 42 pixels on the right" (or bottom) appear,
typically when a `Row`/`Column` is placed inside another layout without
explicit size constraints, and especially when content grows -- longer
text, more children, or a larger accessibility font scale.

## Likely causes
1. **A `Row`'s children combined intrinsic width exceeds available
   width** (e.g. long unwrapped text next to a fixed-width icon) with no
   `Expanded`/`Flexible` or text-overflow handling on the flexible child.
2. **A `Column` nested inside another `Column` or a
   `SingleChildScrollView`/`ListView` without a bounded height**, causing
   the classic "unbounded height" RenderFlex failure when children's
   combined height exceeds the parent's actual constraint.
3. **Fixed-size widgets** (hardcoded widths, fixed padding/margins) that
   don't account for smaller screens, increased system text scale, or
   longer localized strings than the original design language.
4. **Improperly nested scrollables** -- e.g. a `ListView` inside a
   `Column` without `Expanded`/`Flexible` or a bounded height on the
   inner ListView -- producing either an overflow or an "unbounded
   height" assertion depending on the exact nesting.

## Diagnose
- Read the overflow error's exact wording -- it names the direction and
  pixel amount, and the console also names the specific RenderFlex's
  approximate widget-tree location.
- Use the Flutter Inspector's "Select Widget Mode" to tap directly on the
  yellow-striped indicator in the running app and jump straight to the
  offending widget.
- Reproduce with an artificially long text string, a narrower simulated
  screen width, and an increased system font scale (DevTools' text scale
  slider, or device accessibility settings) to identify which content
  length triggers it.
- Check whether the overflowing Row/Column's parent provides bounded
  constraints at all -- e.g. it may be inside a `SingleChildScrollView`
  whose scroll axis leaves the cross axis unbounded.

## Fix
- Wrap the child that should absorb extra or insufficient space in
  `Expanded` (fills remaining space) or `Flexible` (allows shrinking) so
  the Row/Column negotiates space instead of asking every child for its
  natural size.
- For text specifically, add `overflow: TextOverflow.ellipsis` with the
  `Text` wrapped in `Expanded`/`Flexible` so it has a bounded width to
  wrap or ellipsize within, or allow wrapping via `softWrap`/`maxLines`.
- When nesting sized content inside a scrollable, give the inner content
  explicit bounds -- `Expanded` inside a bounded parent, or
  `shrinkWrap: true` with `NeverScrollableScrollPhysics` on an inner list
  meant to size to its content -- rather than leaving height unconstrained.
- Test layouts at 1.3x-2x system font scale and with a long placeholder
  string during development so the design tolerates growth, not just the
  default language and default scale.

## Pitfalls
- Wrapping the offending widget in a `SingleChildScrollView` to make the
  overflow go away merely hides the symptom by making it scrollable
  instead of fixing the layout's space negotiation, often producing an
  unintended scroll area.
- Overusing `Expanded` on multiple children without `flex` factors that
  reflect the intended proportions can fix the overflow while silently
  breaking the intended visual balance -- verify the result looks right,
  not just that the error disappeared.

## Verify
Reproduce the exact original trigger (the specific screen, data, and
font-scale combination that caused the error) and confirm both the
console error and the yellow-striped overlay are gone, then additionally
test at maximum system font scale and with a long test string to confirm
the fix holds under content growth, not just the originally reported case.
