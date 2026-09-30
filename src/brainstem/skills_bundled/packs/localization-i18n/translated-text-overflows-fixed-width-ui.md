---
name: translated-text-overflows-fixed-width-ui
description: A translated string is significantly longer than its English source and overflows or gets truncated inside a fixed-width button, label, or nav item.
triggers: ["german translation too long for button", "text truncated after translation", "finnish translation breaks layout", "button label overflows in localized ui", "translated string wraps and breaks design"]
permissions: ["READ"]
---

## Symptom
A UI element (button, nav tab, form label, badge, table header) is sized to fit its English text comfortably, but after translation the same element either truncates the text mid-word with an ellipsis, overflows its container and overlaps adjacent elements, or forces an ugly line-wrap that breaks the intended one-line layout. This is a well-known recurring issue for languages like German and Finnish, whose compound-word translations routinely run 30-200% longer than the English source (e.g. "Settings" -> "Einstellungen", "Search" -> "Etsi" is fine, but longer UI phrases regularly expand well past the English footprint), and it typically isn't caught until a specific locale's translations are actually loaded into the real UI, because English-only development never exercises the length variance.

## Likely causes
1. **UI elements are sized with a fixed pixel or fixed character-count width** derived from the English string's length, rather than a flexible width that accommodates variable content, so any translation longer than the original simply doesn't fit.
2. **Design and development happen English-only**, with translations added late (often via an external localization vendor after the UI is built and frozen), so no one exercises the actual rendered width of longer-language strings until after layout decisions are already locked in.
3. **Text-overflow handling defaults to silent truncation** (`text-overflow: ellipsis`, `overflow: hidden`, or a fixed-height container that clips a second line) which hides the symptom instead of surfacing it -- the button "looks fine" (doesn't visibly break) while actually cutting off meaningful text, so it can ship without anyone noticing the wording is incomplete.
4. **No length budget or pseudolocalization step exists in the translation/review pipeline**, so translators aren't told a string has a strict character or pixel budget and have no way to know their (linguistically correct) longer phrasing will be clipped by the UI before it ever gets tested.

## Diagnose
- Identify the specific element and locale from the report, and measure the rendered text width in the actual browser/app (not an estimate) at the same font, weight, and size the production UI uses, comparing it against the container's actual computed width/constraints.
- Check the CSS/layout for fixed `width`, fixed `height` combined with `overflow: hidden`, or `white-space: nowrap` on the affected element -- these are the direct mechanisms that convert "longer translation" into "visibly broken or truncated UI."
- Run a pseudolocalization pass (a build mode that expands every string by ~30-50% and wraps it in accented characters, e.g. `[Ŝéttîñgš !!!]`) across the affected screens even without real translations loaded -- this deterministically surfaces every fixed-width element that can't handle length variance, before a real translator ever produces the specific overflowing string.
- Check whether the string in question is one of the categories known to expand significantly (German/Finnish/Russian/Polish compound or agglutinative forms, or any string that was short in English specifically because English allows terse imperatives like "Save"/"Go") -- some languages have no equivalent single short word and require a full phrase.

## Fix
Design fixed UI chrome (buttons, nav items, badges, labels) to accommodate flexible content width by default -- `min-width` instead of fixed `width`, `white-space: normal` with sensible line-wrapping instead of forced `nowrap`, and container layouts (flexbox/grid) that reflow around variable-length children rather than assuming a single character count. Where a truly fixed width is unavoidable (a square icon-button, a fixed-column table), design the interaction for graceful truncation with an accessible full-text fallback (a `title`/tooltip attribute exposing the untruncated string, or a "more" affordance) rather than silent invisible clipping, and set a translator-facing length guideline for that specific slot so translations are written to fit rather than fixed after the fact. Build a pseudolocalization mode into the development/QA pipeline so layout breakage is caught during development against synthetic expanded strings, before waiting for real translations to arrive from a vendor.

## Pitfalls
- Fixing the immediate reported string by manually shortening just that one translation (creating an abbreviated, awkward, or less clear phrasing solely to fit the button) treats the symptom instance-by-instance instead of fixing the underlying fixed-width assumption, so the same breakage recurs for the next long translation or next locale added.
- Silently truncating with `text-overflow: ellipsis` without an accessible way to read the full text (no tooltip, no aria-label with the complete string) hides the bug visually while leaving users unable to read a critical label -- especially problematic for buttons whose meaning changes entirely when clipped (e.g. "Don't save" clipped to "Don't...").
- Testing layout fixes only in the locale that originally reported the bug (commonly German) without checking other long-expanding locales (Finnish, Russian, Polish, or right-to-left languages combined with length changes) means the fix may not generalize, since different languages expand different specific strings by different amounts.

## Verify
Load the affected screen with pseudolocalized strings (or the real longest-expanding locale translations available) and confirm the element resizes, wraps, or truncates-with-accessible-fallback gracefully rather than visually breaking or silently clipping meaningful content -- check at minimum one compounding language (German or Finnish) and, if the product supports RTL, one RTL locale together with a long translation, since both length and direction changes can interact.
