---
name: cls-web-font-flash-unreserved-space
description: Fix layout shift that happens when a custom web font finishes downloading and swaps in over a fallback font of different metrics.
triggers: ["text jumps when font loads", "CLS from web fonts", "FOUT layout shift", "flash of unstyled text", "font swap causes shift"]
permissions: ["READ"]
---

## Symptom
Chrome's CLS score is flagged, and specifically the shift happens a
fraction of a second after text first appears -- line lengths change,
text reflows to a new number of lines, or headings visibly resize as a
custom web font replaces the initial fallback font (FOUT) or replaces
invisible text (FOIT).

## Likely causes
1. **No `font-display` strategy set** (or `font-display: auto`, which
   defaults to browser-specific FOIT behavior), so the browser either
   hides text until the font loads or swaps it in unpredictably.
2. **The fallback font's metrics (character width, line height, x-height)
   differ significantly from the web font's metrics**, so even a fast swap
   causes visible reflow because the same text takes different horizontal
   /vertical space in each font.
3. **The font isn't preloaded**, so it starts downloading only after CSS
   is parsed and the font is actually needed, widening the window during
   which the fallback is shown and then swapped.
4. **Multiple font weights/styles load separately without being
   accounted for**, so bold or italic text (using a different font file)
   shifts independently of the regular-weight text on the same page.

## Diagnose
- Open DevTools > Performance, record page load, and look at the
  "Layout Shift" entries in the Experience track -- click one to see which
  DOM nodes moved and their before/after rects.
- In DevTools > Network, filter by "Font" and check when each font file
  finishes loading relative to when text first painted (visible in the
  Performance trace's paint markers) -- a large gap confirms a visible
  swap window.
- Use the Lighthouse report's "Avoid large layout shifts" audit, which
  lists the specific elements and their shift scores, to confirm text
  elements (not images/ads) are the source.
- Compare the fallback font stack's fallback font metrics against the
  actual web font using a tool like Fontaine or manually comparing
  computed line-height/width for the same string in both fonts.

## Fix
Reserve visual space that already matches the incoming font as closely as
possible, rather than trying to eliminate the swap entirely (which usually
isn't realistic for custom fonts). Concretely: set `font-display: swap` (or
`optional` if a slightly-wrong font on first paint is acceptable to avoid
any shift at all) so text isn't invisible while waiting; use
`size-adjust`, `ascent-override`, `descent-override`, and
`line-gap-override` in an `@font-face` fallback declaration (or a
generator like Fontaine/Capsize) to make the fallback font's box metrics
match the web font's, so the swap doesn't change line count or box size;
and preload the critical font file(s) with `<link rel="preload"
as="font" type="font/woff2" crossorigin>` so the swap window is as short
as possible for the fonts actually used above the fold.

## Pitfalls
- `font-display: block` (long FOIT) avoids the *shift* by hiding text but
  trades it for invisible text and worse perceived performance/LCP if the
  LCP element is text -- know which tradeoff you're making, don't pick
  `block` reflexively.
- Preloading every font weight/style used anywhere on the site (instead of
  just the ones needed for above-the-fold content) delays other critical
  resources and can hurt LCP more than it helps CLS.
- Matching fallback metrics for the wrong fallback font (e.g. tuning
  against the OS's default sans-serif when the actual computed fallback in
  the font stack is different) doesn't fix anything -- verify the actual
  fallback being used via computed styles.

## Verify
Reload with a throttled network (Slow 4G in DevTools) so the swap window
is visible, confirm no Layout Shift entries appear in the Performance
trace's Experience track for the text elements, and re-check the page's
CLS value in Lighthouse/PageSpeed or field data (CrUX/`web-vitals`)
afterward.
