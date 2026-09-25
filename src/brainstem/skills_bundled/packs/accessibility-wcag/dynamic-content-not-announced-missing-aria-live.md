---
name: dynamic-content-not-announced-missing-aria-live
description: Fix toast notifications or dynamically updated content that appear visually but are never announced to screen reader users.
triggers: ["toast not announced by screen reader", "aria-live not working", "dynamic content not read aloud", "notification silent for screen reader", "live region doesn't announce"]
permissions: ["READ"]
---

## Symptom
A toast notification ("Item added to cart," "Settings saved"), an
inline status update, or a counter that updates in place (a "3 new
messages" badge, a search results count) appears and disappears
correctly on screen for sighted users, but a screen reader user gets no
announcement at all -- they have no way of knowing the action succeeded
or that anything changed unless they happen to navigate directly to
that part of the page afterward.

## Likely causes
1. **No `aria-live` region exists anywhere in the relevant DOM** -- the
   toast is just a styled `div` that mounts and unmounts via
   conditional rendering, with nothing telling assistive tech to treat
   changes to it as announcement-worthy.
2. **The live region is created and populated in the same render/DOM
   operation** -- e.g. a toast component that mounts a fresh `<div
   aria-live="polite">Item added</div>` node with the text already
   inside it at creation time. Many screen readers only announce
   content *mutations* to a region that was already present and empty;
   inserting a whole new node with text already set can be missed.
2b. **The live region is removed from the DOM immediately after (or
   very quickly after) being populated**, which can race with the
   screen reader's announcement timing and cause it to be dropped
   silently, especially for `aria-live="polite"` competing with other
   page activity.
3. **The wrong live-region politeness or role is used for the content's
   urgency** -- a critical error uses `aria-live="polite"` (which waits
   for a pause and can be skipped entirely if superseded by another
   update) when it should be `assertive`/`role="alert"`, or conversely
   a low-priority status update is marked assertive and rudely
   interrupts whatever the screen reader was already reading.
4. **The live region is present but hidden via `display:none` at the
   time content is inserted**, then shown afterward with CSS -- some
   screen readers only pick up updates to regions that are already
   rendered/visible in the accessibility tree, not ones toggled visible
   at the same time as the content change.

## Diagnose
- Inspect the DOM at the moment the toast/update appears: is there a
  persistent element with `aria-live` (or `role="status"`/`role=
  "alert"`) that already existed before the content changed, or is a
  brand-new node created with the text already inside it?
- With a screen reader running, trigger the update and listen -- note
  whether it's silent, delayed, or cut off (cut off often indicates a
  region that's removed too quickly after being populated).
- Check the region's `aria-live` value and compare it to the content's
  actual urgency -- a save confirmation should generally be `polite`;
  a form submission failure or session-timeout warning should be
  `assertive`.
- Use the browser's Accessibility tree view (not just the DOM) to
  confirm the live region node is actually present in the accessibility
  tree (not `display:none` or `aria-hidden`) at the moment of update.

## Fix
Keep a persistent, empty live-region container mounted in the DOM at
all times (not created fresh per message), and update its text content
in place when there's something to announce -- this is the mutation
screen readers reliably detect. Choose politeness deliberately: `aria-
live="polite"` (or the equivalent `role="status"`) for confirmations
and non-urgent status changes that shouldn't interrupt the user;
`aria-live="assertive"` (or `role="alert"`, which is implicitly
assertive) only for time-sensitive or error content that genuinely
needs to interrupt. Give the message enough time to be announced before
removing it (a few seconds at minimum for a toast that auto-dismisses)
rather than tying its DOM lifetime tightly to a fast CSS fade-out
animation. For counters/badges, ensure the live region wraps the
specific text that changes ("3 new messages") rather than a whole
container where unrelated re-renders could cause spurious or duplicate
announcements.

## Pitfalls
- Wrapping the *entire* toast container (icon, dismiss button, message)
  in the live region can cause a screen reader to announce
  interactive-control noise ("button") alongside the message, or
  double-announce it if the button itself is separately focusable
  inside the region -- scope the live region to just the text content.
- Overusing `aria-live="assertive"` for routine confirmations causes
  frequent interruptions that make screen reader use of the page
  fatiguing and often gets it disabled or ignored via user-side
  workarounds.
- Toggling a live region between hidden and visible with the same
  operation that sets its text can be missed by some screen readers --
  keep the region visible (or at minimum present in the accessibility
  tree) and only change its text content.

## Verify
With a screen reader active, trigger the dynamic update (submit the
form, add the item, wait for the counter to change) and confirm the
message is announced automatically without the user needing to
navigate to it, at a politeness level matching its urgency, and confirm
it isn't cut off before the announcement completes.
