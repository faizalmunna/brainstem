---
name: image-layout-shift-before-load
description: Stop images or embedded media from causing a visible layout jump when they finish loading without reserved space.
triggers: ["page jumps when image loads", "layout shift on image load", "content jumps down after images load", "CLS from images", "images push content around"]
permissions: ["READ"]
---

## Symptom
Surrounding content visibly jumps (usually downward) the moment an image,
video, or embed finishes loading, most noticeable on slower connections
or with many images on one page -- measurable as Cumulative Layout Shift
(CLS) in Lighthouse/PageSpeed Insights, and directly reproducible by
throttling network speed and watching the page render.

## Likely causes
1. **No `width`/`height` attributes (or aspect-ratio CSS) on the
   `<img>`/`<video>` element**, so the browser has no way to reserve space
   before the file downloads and reports its intrinsic dimensions -- the
   element occupies zero height until the image loads, then suddenly
   expands.
2. **A `width`/`height` set only via CSS on one axis** (e.g. `width:
   100%` with no height rule and no `aspect-ratio`), which still leaves
   the height undetermined until the image loads and its natural
   aspect ratio becomes known.
3. **Responsive images (`srcset`/`sizes`, or art-directed `<picture>`
   sources)** where different sources have different aspect ratios, so
   even a fixed height reserved for one breakpoint doesn't match what
   actually loads at another.
4. **Third-party embeds (ads, social embeds, iframes)** that inject their
   own content asynchronously with no placeholder sizing at all, which
   behaves the same way but often isn't caught in a code review because
   the embedding site doesn't control the injected markup directly.
5. **Web fonts causing a secondary shift right after the image loads**
   (FOUT/FOIT) that gets misattributed to the image, when it's actually
   an unrelated `font-display` issue happening at a similar time in the
   load sequence.

## Diagnose
- Run Chrome DevTools' Performance panel with "Web Vitals" checkboxes
  enabled, or Lighthouse, and look for CLS entries -- clicking one
  highlights exactly which element shifted and by how much.
- Throttle network to "Slow 3G" in DevTools' Network panel and visually
  watch the page load to see which specific image/embed causes the jump
  and what shifts around it.
- Check the `<img>` element's HTML/computed styles for `width` and
  `height` attributes or an `aspect-ratio` CSS rule; their absence
  together with an unset height is the direct cause to confirm.

## Fix
Always set `width` and `height` attributes on `<img>`/`<video>` elements
matching their intrinsic aspect ratio (modern browsers use these to
compute an `aspect-ratio` automatically even when CSS overrides the
rendered width), or set `aspect-ratio: <w> / <h>` explicitly in CSS
alongside a fluid `width: 100%` so the box reserves correct height at any
rendered width. For responsive art-direction where aspect ratio genuinely
changes per breakpoint, set a different `aspect-ratio` per breakpoint via
media query rather than leaving it unset. For third-party embeds, wrap
them in a container with a fixed or `aspect-ratio`-based min-height
matching the embed's typical size, accepting a placeholder gap rather than
no reservation at all.

## Pitfalls
- Setting only `width` and `height` as CSS pixel values (not `aspect-
  ratio` or the HTML attributes) can fight with responsive `max-width:
  100%` rules and either not reserve the right space or force incorrect
  aspect ratios on other breakpoints -- prefer `aspect-ratio` for fluid
  layouts.
- Reserving space for a third-party embed with a guessed fixed height
  that doesn't match what actually loads (e.g. an ad that later renders
  taller) just moves the shift to whenever the embed resolves, rather
  than eliminating it -- verify against the embed's actual rendered
  size, not an assumption.

## Verify
Re-run Lighthouse or the Performance panel's Web Vitals measurement on
the page and confirm the CLS score for that element drops to
effectively zero, and visually re-check under throttled network that the
surrounding content no longer moves once the image/embed finishes
loading.
