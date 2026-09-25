---
name: playwright-visual-regression
description: Set up Playwright visual regression (screenshot) testing that catches real visual bugs without becoming so noisy from harmless rendering differences that the team ignores it.
triggers: ["visual regression test flaky", "screenshot test always fails", "playwright screenshot diff", "visual test noise", "screenshot comparison ci vs local differs"]
permissions: ["READ"]
---

## Symptom
Visual regression (screenshot comparison) tests fail constantly for
reasons unrelated to a real visual bug -- font rendering differences
between local and CI, animation frames captured mid-transition, dynamic
content (timestamps, ads, randomized data) differing between runs -- to
the point where the team starts reflexively approving every diff without
looking, which defeats the purpose of the check.

## Likely causes
1. **Font/rendering differences between the environment that generated
   the baseline and the environment running the comparison** (local
   machine's OS font rendering vs. CI's headless browser/OS, or different
   Playwright/browser versions producing subtly different anti-aliasing).
2. **Screenshots taken while an animation/transition is mid-flight**,
   capturing a different frame each run even with no actual visual
   change.
3. **Dynamic, non-deterministic content in the captured area**:
   timestamps, relative dates ("2 minutes ago"), randomly-ordered lists,
   third-party embeds/ads, or a cursor blink -- anything that legitimately
   differs between runs without being a bug.
4. **Screenshotting the full page** when only a specific component is
   under test, so unrelated changes anywhere on the page (a banner, a
   footer) trigger unrelated diffs.

## Diagnose
- Check whether baselines were generated in the same environment
  (browser version, OS, Playwright version) that CI uses for comparison
  -- a mismatch here is the single most common cause of constant,
  meaningless diffs.
- Inspect a few "false positive" diffs directly: do they show a genuine
  pixel-level rendering artifact, a mid-animation frame, or actual
  dynamic content, versus an actual layout/style change?
- Check the scope of each screenshot: full-page vs. a specific,
  intentionally-scoped element/region.

## Fix
- Generate and update baselines in the exact same environment
  configuration CI uses (commonly: run baseline generation inside the
  same Docker image/CI runner, not on a developer's local machine) so
  font/rendering differences don't factor in at all.
- Disable or freeze animations/transitions before capturing (Playwright's
  `animations: 'disabled'` screenshot option, or waiting for a specific
  "animation complete" signal) so the captured frame is deterministic.
- Mask or exclude genuinely dynamic regions (timestamps, ads, live data)
  from the comparison -- Playwright's screenshot options support masking
  specific locators -- rather than trying to make that content
  deterministic when it fundamentally isn't.
- Scope screenshots to the specific component/region under test rather
  than the full page, so unrelated changes elsewhere don't produce
  irrelevant diffs for a test that isn't about that region.
- Set an appropriate pixel-difference threshold (Playwright's
  `maxDiffPixelRatio`/`threshold` options) to tolerate genuinely
  negligible anti-aliasing noise without hiding real changes -- tune this
  empirically against known-good and known-bad examples, not a guess.

## Pitfalls
- Raising the diff threshold high enough to stop all false positives can
  also hide real, meaningful visual regressions (e.g. a broken layout
  that only shifts a modest number of pixels) -- fix the actual sources
  of nondeterminism first, and treat threshold tuning as a last resort
  for genuine, irreducible noise.
- A team that's been burned by noisy visual tests tends to start
  rubber-stamping every diff approval -- if that's already happened,
  treat rebuilding trust (a period of genuinely reliable, low-noise
  results) as part of the fix, not just the technical changes.

## Verify
Run the visual test suite multiple times in a row in the CI environment
with zero code changes and confirm zero diffs; then deliberately introduce
a real, visible style regression and confirm the suite catches it.
