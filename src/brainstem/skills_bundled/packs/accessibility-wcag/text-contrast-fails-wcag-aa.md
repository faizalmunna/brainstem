---
name: text-contrast-fails-wcag-aa
description: Fix body or label text that looks fine to designers but fails the WCAG AA 4.5:1 contrast ratio against its background.
triggers: ["contrast checker fails", "wcag aa contrast", "text fails color contrast audit", "lighthouse contrast issue", "gray text too light accessibility"]
permissions: ["READ"]
---

## Symptom
An accessibility audit (Lighthouse, axe, a manual contrast checker) flags
text as failing WCAG 2.1 AA contrast (4.5:1 for normal text, 3:1 for
large text at 18pt+/14pt+bold), even though the text passed visual design
review and looks legible to most sighted reviewers on a calibrated
monitor in good lighting. Common instances: light gray body text on
white, placeholder text, disabled-looking buttons that are actually
interactive, and white text over a background image or gradient where
contrast varies by region.

## Likely causes
1. **A design system's "muted"/"secondary" gray token was chosen for
   visual hierarchy (to look subtly de-emphasized) without ever
   computing its contrast ratio** -- something like `#999` on `#fff`
   yields ~2.8:1, well under the 4.5:1 minimum, despite looking
   acceptable at a glance on a good display.
2. **Text sits on a background image, gradient, or semi-transparent
   overlay** where contrast is computed (if at all) against one sample
   point but fails at other points behind the same text -- a gradient
   that's dark on the left and light on the right will fail wherever the
   text crosses into the lighter region.
3. **Placeholder text or disabled-state styling is reused for text that
   is not actually disabled** -- input placeholders and truly disabled
   controls are exempt from some contrast requirements, but that same
   faint styling gets applied to real, interactive, always-visible
   labels or button text by a shared "muted" class.
4. **Contrast was checked once, in light mode, and never re-verified in
   dark mode** (or vice versa) -- a color pair tuned to pass in one
   theme often fails in the other because the token maps to a different
   underlying hex value.

## Diagnose
- Use a contrast checker (WebAIM Contrast Checker, or the contrast ratio
  shown directly in Chrome DevTools when inspecting a text element's
  color in the Styles pane) and plug in the actual computed foreground
  and background hex values -- not the values in a design mockup, which
  may differ after CSS variables/opacity are applied.
- Run Lighthouse's or axe's accessibility audit on the live rendered
  page (not the design file) -- it reports every element failing the
  ratio along with its computed colors.
- For text over images/gradients, sample the background color at
  multiple points behind the text (not just the center) using the
  browser's eyedropper/color-picker devtool, since a single sample can
  miss the worst-case region.
- Check both light and dark theme variants separately if the site
  supports theme switching -- audit each as its own pass.

## Fix
Treat contrast as a hard constraint on the token itself, not a per-
instance tweak: adjust the "muted"/"secondary" text color in the design
system so it clears 4.5:1 against every background it's actually used
on (usually means darkening a gray token by a fixed number of lightness
steps), and propagate that single token change everywhere it's
referenced rather than patching individual components. For text over
images or gradients, add a solid or gradient scrim (a semi-transparent
dark or light overlay) between the image and the text so the effective
background the text sits on has a computed, predictable color you can
verify, rather than relying on the image's variable luminance. For
large/bold text intentionally using the relaxed 3:1 threshold, confirm
it actually qualifies under the WCAG size definition (18pt+/24px+
regular, or 14pt+/18.66px+ bold) rather than assuming any large-looking
text qualifies.

## Pitfalls
- Fixing the failing text by darkening it just enough to pass 4.5:1
  exactly at one background color, without checking it against every
  surface the token is reused on (cards, hover states, dark mode),
  reintroduces the failure somewhere else.
- Increasing font weight or size to compensate for insufficient contrast
  addresses a *different* WCAG success criterion (large text has a lower
  threshold) but doesn't fix the actual color pair for any surface where
  the text remains normal-sized.
- Relying solely on an automated scanner's pass/fail misses gradient and
  image-background cases where contrast varies by region -- automated
  tools typically sample one point and can report a false pass.

## Verify
Re-run the contrast checker against the final rendered computed colors
(via DevTools, not the design file) and confirm at least 4.5:1 for
normal text or 3:1 for qualifying large text, in every theme variant the
site supports, and at the worst-case sampled point for any text over an
image or gradient.
