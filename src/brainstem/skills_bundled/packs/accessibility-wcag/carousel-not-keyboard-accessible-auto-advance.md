---
name: carousel-not-keyboard-accessible-auto-advance
description: Fix an image carousel or slider that keyboard users cannot operate and that auto-advances slides with no way to pause it.
triggers: ["carousel not keyboard accessible", "slider auto advances no pause button", "carousel arrows not focusable", "wcag carousel violation", "slideshow keeps moving screen reader"]
permissions: ["READ"]
---

## Symptom
A hero carousel or content slider on a landing page rotates through
slides automatically every few seconds. A keyboard user tabbing through
the page either can't reach the next/previous controls at all (they're
`div`s with only click handlers), or can reach them but the slide
advances out from under them before they finish reading it because
there's no way to pause the rotation. A screen reader user navigating
the page hears slide content change or repeat unpredictably as the
carousel auto-advances mid-navigation, and dots/thumbnails indicating
the current slide are announced as unlabeled generic elements if
announced at all.

## Likely causes
1. **Next/previous controls and pagination dots are built from `div`s
   or `span`s with only `onClick` handlers**, with no `tabindex`, no
   `button` semantics, and no keyboard event handling -- the same
   underlying issue as any custom-control-without-native-semantics bug,
   applied here to carousel navigation specifically.
2. **Auto-rotation runs on a fixed interval with no pause/stop
   control exposed anywhere in the UI** -- this directly violates WCAG
   2.2.2 (Pause, Stop, Hide), which requires user control over any
   auto-updating content that moves, blinks, or scrolls for more than
   five seconds.
3. **Auto-rotation doesn't pause on focus or hover**, so even if a user
   does manage to focus a link or button inside the current slide, the
   slide can rotate away mid-interaction, taking the focused element
   out of view or replacing it entirely.
4. **Slide content isn't marked up so screen readers announce slide
   position** (no "slide 2 of 5" equivalent via `aria-roledescription`/
   `aria-label` on each slide, no live region announcing the change),
   so screen reader users get no orientation about what's happening as
   content changes.

## Diagnose
- Tab through the carousel region and confirm every control (previous,
  next, each pagination dot) is reachable and shows a visible focus
  indicator.
- Time the auto-rotation interval and look for any visible pause/stop
  control -- WCAG requires one if a cycle runs longer than five seconds
  and auto-starts.
- Focus a link inside the currently visible slide and wait through a
  full rotation interval without touching anything else -- does the
  slide change anyway, taking the focused element out of view or
  replacing it while it still has focus?
- With a screen reader running, let the carousel rotate at least twice
  while not otherwise interacting, and note whether slide changes are
  announced at all or announced so frequently they interrupt other
  navigation.

## Fix
Build carousel controls as real `<button>` elements (inherently
focusable, keyboard-activatable, and correctly announced) for previous/
next and each pagination dot, with `aria-label`s identifying their
target ("Go to slide 3 of 5") rather than relying on visual icons
alone. Provide an explicit, always-visible pause/play control, and pair
it with automatic pausing whenever any element inside the carousel
receives keyboard focus or mouse hover, resuming only after focus/hover
leaves and, ideally, only if the user hasn't explicitly paused it.
Structure each slide as a labeled group (`role="group"` with `aria-
roledescription="slide"` and an `aria-label` like "3 of 5") so screen
readers give positional context, and if slide changes should be
announced, use a single polite live region for the transition rather
than re-announcing full slide content on every rotation. For content
that isn't essential to communicate in real time, seriously consider
whether auto-rotation is needed at all -- a static set of cards with
manual navigation avoids this entire class of issue.

## Pitfalls
- Adding a pause button but leaving the default rotation running
  whenever a slide's own link or button gets keyboard focus still
  yanks focus/content away from a user who tabbed into a slide but
  hasn't explicitly hit pause -- focus and hover should pause
  automatically, not require a separate deliberate action.
- Making pagination dots into `<button>`s but leaving their accessible
  name as the visual dot's default (nothing, or "•") means screen
  reader users hear "button" repeated with no way to tell one dot from
  another -- each needs a distinct label.
- Switching to `aria-live` announcements on every auto-rotation without
  throttling produces constant interruptions for screen reader users
  even after they've stopped actively engaging with the carousel,
  which is often worse than no announcement.

## Verify
Tab to the carousel, confirm every control is reachable with a visible
focus indicator and correct labels, confirm a pause control exists and
stops rotation when activated, and confirm that simply focusing a link
inside the current slide (via Tab, without touching pause) prevents
that slide from being auto-advanced away.
