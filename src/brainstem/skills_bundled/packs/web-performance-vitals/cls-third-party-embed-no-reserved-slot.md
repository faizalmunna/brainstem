---
name: cls-third-party-embed-no-reserved-slot
description: Fix layout shift caused by an ad, social embed, or widget script injecting content above existing page content with no space reserved for it.
triggers: ["ad pushes content down", "embed causes layout shift", "CLS from ads", "widget shifts page content", "iframe causes layout jump"]
permissions: ["READ"]
---

## Symptom
The page looks stable, then a moment later an ad slot, a social media
embed (tweet, Instagram post), a cookie-consent banner, or a chat widget
loads and pushes everything below it further down the page -- often right
as the user is about to tap something, causing accidental clicks on the
wrong element.

## Likely causes
1. **The container for the embed has no explicit width/height (or
   `aspect-ratio`) before the third-party script runs**, so it collapses
   to zero height until content is injected, then expands.
2. **The embed's final size is genuinely unknown until its own script
   runs** (ad networks pick a creative size, social embeds fetch oEmbed
   data), so there's no fixed size to reserve without an estimate/reserved
   minimum.
3. **The script that injects the content loads asynchronously and finishes
   at an unpredictable time relative to the rest of the page** (unlike a
   normal image with known intrinsic dimensions), so it can land anywhere
   in the render sequence.
4. **A banner/widget is inserted at the top of the DOM (or fixed-position
   converted to static) after other content has already rendered**, e.g. a
   cookie consent banner added via `document.body.prepend()`.

## Diagnose
- In DevTools > Performance, record the recording through the point the
  embed loads and inspect the Layout Shift entries -- the "Layout Shift"
  details panel names the moved elements and their shift score
  contribution.
- Use `chrome://net-export` or the Network panel to identify exactly which
  third-party script's execution correlates in time with the shift shown
  in the Performance trace.
- Check the ad/embed container's computed CSS at page load (before the
  script runs) via DevTools Elements -- if `height: auto` and no
  `min-height`/`aspect-ratio` is set, that confirms no space is reserved.
- For consent banners, check whether they're inserted with `position:
  fixed`/`sticky` (which doesn't affect layout, no CLS) versus static
  positioning that pushes content (does affect layout, causes CLS).

## Fix
Reserve a slot sized to the *known or expected* dimensions before the
script has a chance to run, so the page's layout doesn't change shape when
content arrives -- the goal is making the container's size independent of
whether the async content has loaded yet. Concretely: set an explicit
`min-height` (or `aspect-ratio` for known-ratio embeds) on the ad/embed
container based on the network's documented standard sizes or the
embed's typical dimensions, so the space exists from first paint; for ad
slots with genuinely variable sizes, reserve the size of the *most common*
outcome and accept that some creative sizes may need to overflow/center
within it rather than resize the container; and use `position: fixed` (or
render consent banners overlaying content, not pushing it) for anything
that must appear immediately without depending on layout-affecting
insertion.

## Pitfalls
- Reserving a large fixed height "to be safe" when most embeds render
  smaller leaves ugly empty whitespace for users who never see the wider
  content -- calibrate the reserved size to the actual real-world
  distribution of embed dimensions, not the worst case.
- Fixing the ad slot but forgetting the consent banner (or vice versa) --
  CLS is cumulative across the whole page load, so partial fixes still
  leave a bad score if any injected element is unreserved.
- Setting `aspect-ratio` on a container without also constraining its
  width means the reserved height can still be wrong if the container's
  width changes at different breakpoints -- verify across viewport sizes.

## Verify
Reload the page with the embed/ad network active (not blocked by an ad
blocker during testing) and confirm no Layout Shift entries appear for
elements below the embed in the Performance trace's Experience track, and
confirm the page's CLS score in Lighthouse/PageSpeed or CrUX field data
improved.
