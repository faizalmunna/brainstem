---
name: oversized-images-wrong-render-dimensions
description: Fix images shipped at a much larger resolution or file size than the dimensions they actually render at on the page.
triggers: ["images too large for lighthouse", "properly size images warning", "oversized images", "image bigger than display size", "serve images in next gen formats"]
permissions: ["READ"]
---

## Symptom
Lighthouse flags "Properly size images" and/or "Serve images in next-gen
formats," and specifically the downloaded image file's pixel dimensions or
byte size are far larger than the space it actually occupies on the
rendered page (e.g. a 3000x2000px photo displayed in a 300x200px card),
wasting bandwidth and hurting LCP/load time without any corresponding
visual benefit.

## Likely causes
1. **A single source image is used across many contexts** (thumbnail,
   card, full detail view) without generating differently-sized variants,
   so the largest needed size is served everywhere for simplicity.
2. **No `srcset`/`sizes` attributes**, so the browser can't pick a
   resolution appropriate to the actual display size and device pixel
   ratio -- it downloads whatever single URL is given, often an
   originally-uploaded, unresized asset.
3. **CMS/user-uploaded images are served as-uploaded** with no automatic
   resizing/transformation pipeline, so image dimensions are whatever the
   original uploader's camera/screenshot produced.
4. **Legacy formats (JPEG/PNG) used where AVIF/WebP would produce
   materially smaller files** at equivalent visual quality, independent of
   the dimension-mismatch problem.
5. **CSS scales down an image with `width`/`height` instead of the image
   being served pre-sized**, which looks correct visually but downloads
   the full original regardless of the CSS-rendered size.

## Diagnose
- Run Lighthouse's "Properly size images" audit, which lists each image's
  actual rendered dimensions versus its natural/downloaded dimensions and
  the potential byte savings.
- In DevTools > Elements, select the image and check the difference
  between the "Rendered size" and "Intrinsic size" shown in the tooltip/
  computed panel -- a large gap confirms oversizing.
- In DevTools > Network, check each image's transferred size and compare
  against a rough expectation for its rendered dimensions at reasonable
  quality (a 300x200 card image shouldn't be multiple hundreds of KB).
- Check whether `srcset`/`sizes` are present on the `<img>` tag, and if
  present, verify in Network which candidate URL was actually chosen at
  the current viewport/DPR.

## Fix
Serve images sized (and encoded) for where they actually render, rather
than relying on the browser or CSS to visually scale down a
larger-than-needed file. Concretely: use an image CDN/transformation
pipeline (or framework image component, e.g. `next/image`, Cloudinary,
Imgix) to generate multiple resolution variants and serve them via
`srcset`/`sizes` so the browser picks the smallest variant that satisfies
the actual rendered size and device pixel ratio; convert to modern
formats (AVIF/WebP) with a fallback for older browsers via `<picture>`
`source` elements or `Accept`-header-based content negotiation at the CDN;
and for user-uploaded content, resize/transcode on upload (or on
first-request, cached thereafter) rather than serving originals directly.

## Pitfalls
- Generating too many `srcset` variants (e.g. every 50px width) adds cache
  fragmentation and CDN storage/processing overhead for negligible
  additional savings -- a reasonable set of breakpoints (e.g. 3-5 sizes)
  usually covers the real-world range.
- Over-compressing to hit a byte-size target can introduce visible
  artifacts on high-DPI displays or photography-heavy content -- balance
  file size against visual quality for the specific image content, don't
  apply one compression setting universally.
- Serving AVIF/WebP without a fallback breaks images entirely in older
  browsers/email clients that don't support them -- verify fallback
  behavior, not just the modern-browser happy path.

## Verify
Re-run Lighthouse's "Properly size images" audit and confirm the flagged
images no longer appear (or their potential-savings estimate drops near
zero), and spot-check in DevTools Network that the transferred image size
for representative pages is proportional to their actual rendered
dimensions at common device pixel ratios (1x, 2x, 3x).
