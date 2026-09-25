---
name: lcp-hero-image-missing-priority-hints
description: Diagnose a poor LCP score caused by the hero image loading late because it lacks fetchpriority or preload and lazy-loading was applied where it shouldn't be.
triggers: ["LCP is red in PageSpeed", "hero image loads slowly", "largest contentful paint is slow", "fetchpriority hero image", "lazy loading hurting LCP"]
permissions: ["READ"]
---

## Symptom
PageSpeed Insights/Lighthouse reports a poor LCP score (>2.5s), and the
flagged "LCP element" is the above-the-fold hero image or banner --
visually, the page shows layout and text almost immediately but the big
image pops in noticeably late.

## Likely causes
1. **The browser doesn't discover the image early** because it's set via
   CSS `background-image` (invisible to the preload scanner) or injected
   by JavaScript after hydration, instead of a plain `<img>` in the
   initial HTML.
2. **`loading="lazy"` was applied to the LCP image itself**, often because
   a blanket "lazy-load all images" convention was applied without
   excepting the one image guaranteed to be in the initial viewport --
   this actively delays it rather than helping.
3. **The image has no `fetchpriority="high"` or `<link rel="preload">`**,
   so it competes for bandwidth with lower-priority resources (fonts,
   analytics, below-fold images) discovered around the same time and the
   browser has no signal to fetch it first.
4. **The image is served at a much larger byte size than needed** (wrong
   format, no responsive `srcset`, no compression), so even with correct
   priority the download itself is slow, especially on throttled mobile
   connections.
5. **A render-blocking resource (large CSS/font/script) sits ahead of the
   image tag in the document**, delaying when the browser even starts
   fetching it.

## Diagnose
- Run Lighthouse (or Chrome DevTools > Performance panel) and confirm which
  element is flagged as "LCP element" -- don't assume, since sometimes a
  block of text is the real LCP element instead of the image you suspect.
- In DevTools > Network, filter by the image and check its "Priority"
  column -- if it says "Low" or "Medium" instead of "High", the browser
  isn't prioritizing it.
- Check the "Start Time" of the image request relative to the navigation
  start in the waterfall -- a late start time means late *discovery*, not
  a slow download, which points at causes 1 or 5 rather than 3.
- View page source (not just DevTools Elements, which shows the mutated
  DOM) to confirm the image tag and its attributes exist in the initial
  HTML rather than being injected by JS.

## Fix
Give the browser both an early discovery path and an explicit priority
signal for the one image that actually needs it, and stop treating "lazy
load everything" as a universal rule -- lazy-loading exists to *defer*
below-fold images, and the LCP image by definition isn't below fold, so
lazy-loading it is fighting the metric it's supposed to help. Concretely:
render the LCP image as a plain `<img>` in server-rendered HTML (not a CSS
background or JS-injected element) so the browser's preload scanner finds
it during initial HTML parsing, remove any `loading="lazy"` on it, add
`fetchpriority="high"`, and optionally add `<link rel="preload" as="image"
href="...">` in `<head>` for cases where discovery is still late (e.g. the
URL depends on a responsive `srcset` computed client-side). Serve it as a
correctly-sized, modern-format (AVIF/WebP with fallback) image so the
priority boost isn't wasted on unnecessary bytes.

## Pitfalls
- Adding `fetchpriority="high"` or preload to *every* image "just in case"
  dilutes the signal -- the browser can only meaningfully prioritize one or
  two resources this way; reserve it for the actual LCP element.
- Preloading an image that turns out not to be the LCP element (e.g. it
  gets covered by a cookie banner or is below the fold on some viewports)
  wastes bandwidth that should have gone to what really renders first --
  confirm the LCP element per viewport before preloading.
- Switching to responsive `srcset` without also fixing priority/lazy
  attributes just changes which URL loads late, not whether it loads late.

## Verify
Re-run Lighthouse/PageSpeed and confirm the LCP timing metric improved
(not just that the image "looks" faster), and in DevTools Network confirm
the image's Priority column now reads "High" with a Start Time close to
navigation start.
