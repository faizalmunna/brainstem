---
name: rtl-layout-half-mirrored-ui
description: Arabic or Hebrew text reads right-to-left correctly but icons, navigation, and form alignment still visually flow left-to-right, producing a jarring half-mirrored interface.
triggers: ["arabic layout looks broken", "rtl mode only flips text not layout", "hebrew UI icons on wrong side", "half mirrored interface rtl", "back button pointing wrong direction in arabic"]
permissions: ["READ"]
---

## Symptom
Switching the app to an RTL locale (Arabic, Hebrew, Farsi, Urdu) correctly flips paragraph text direction, so sentences read right-to-left, but the surrounding chrome doesn't follow: the primary navigation is still on the left, a "back" chevron still points left (implying forward in RTL reading order), form labels stay left-aligned above right-aligned text fields, a hamburger menu still opens from the left edge, and icons like "next" arrows or progress indicators point the wrong semantic direction. The result reads as a translation applied to an otherwise-untouched LTR skeleton rather than a truly mirrored RTL experience.

## Likely causes
1. **CSS uses physical properties (`left`, `right`, `margin-left`, `text-align: left`) instead of logical properties** (`inset-inline-start`, `margin-inline-start`, `text-align: start`), so setting `dir="rtl"` on the document flips text rendering (a browser default) but every explicit physical-direction style the app authored stays pinned to its literal side.
2. **The RTL switch is implemented as a translation-only concern** (swap the string catalog) without an accompanying layout-direction pass, because the team treated "add Arabic" as a translation task rather than a bidi (bidirectional) layout task with its own component-level requirements.
3. **Iconography is directional but not mirrored** -- back/forward chevrons, "send" arrows, playback controls, and progress/breadcrumb indicators are shipped as fixed image assets or icon-font glyphs with no RTL variant or CSS `transform: scaleX(-1)` rule, so they keep pointing in their original direction regardless of `dir`.
4. **Third-party components or a subset of the app (e.g. an embedded iframe widget, a chart library, a legacy module) don't respond to `dir` at all**, because they were built assuming LTR and don't read the ambient direction or expose an RTL mode, so they sit as an LTR island inside an otherwise-mirrored page.
5. **`dir="rtl"` is applied inconsistently** -- set on a top-level wrapper but not propagated to portaled content (modals, tooltips, dropdowns rendered outside the normal DOM tree via portals), so those elements silently fall back to the browser's LTR default even though the rest of the page is mirrored.

## Diagnose
- Set the document or root container to `dir="rtl"` and visually diff the whole page against its LTR version -- specifically check: which edge the primary nav/sidebar is on, which direction "next/back" icons point, where the scrollbar renders, and whether form field labels and alignment flipped with the text.
- Search the stylesheet for physical directional properties (`left:`, `right:`, `margin-left`, `padding-right`, `text-align: left/right`, `float: left/right`) -- each one is a candidate that won't respond to `dir` and needs to become a logical-property equivalent.
- Inspect portaled elements (modals, toasts, dropdown menus, tooltips) in the browser devtools to see whether they inherited `dir="rtl"` from an ancestor or were rendered into a DOM node outside that ancestor's subtree (common with `ReactDOM.createPortal` or similar) and thus default to LTR.
- Check icon usage for direction-sensitive glyphs (arrows, chevrons, "undo/redo", playback/seek controls) and confirm whether the icon set has a mirrored variant or a CSS rule conditionally flipping it under `[dir="rtl"]`.
- Load any embedded third-party widget or library-rendered component (rich chart, calendar picker, code editor) under `dir="rtl"` specifically, since these are the most common LTR islands.

## Fix
Treat RTL as a layout-direction requirement, not a translation string-swap: migrate directional CSS from physical properties to logical properties (`margin-inline-start/end`, `padding-inline-start/end`, `inset-inline-start/end`, `text-align: start/end`) so the same stylesheet automatically mirrors correctly whenever `dir` changes, instead of maintaining parallel LTR/RTL stylesheets. For iconography, classify icons as directional (arrows, chevrons, send/reply, forward/back) versus non-directional (search, settings, trash), and apply a mirroring rule (CSS `transform: scaleX(-1)` scoped to `[dir="rtl"] .icon-directional`, or a distinct RTL icon asset) only to the directional set -- mirroring non-directional icons like a magnifying glass produces a different, equally jarring bug. Ensure `dir` is set at a level that all portaled UI inherits from (or explicitly propagate it to each portal root), and audit every third-party embed for RTL support, wrapping or replacing ones that can't mirror themselves.

## Pitfalls
- Wrapping the entire page in `transform: scaleX(-1)` as a shortcut "mirrors everything at once" but also flips text rendering into backwards mirrored glyphs and breaks any content that must stay unmirrored (logos, numerals in some contexts, embedded media), so it's not a substitute for a real logical-properties pass.
- Mirroring every icon indiscriminately, including semantically direction-neutral ones (search, settings gear, checkmarks) or icons containing text/numbers, produces icons that look wrong or unreadable -- only direction-implying icons should flip.
- Fixing layout for the top-level page but not testing portaled/overlay components (which are exactly where `dir` inheritance silently breaks) leaves an inconsistent experience that's easy to miss in a cursory review of the main page only.

## Verify
Load the app under an RTL locale and check, on every screen and portaled component (not just the top-level page): navigation and sidebar position mirrored, form label/field alignment mirrored, directional icons (back/forward/send) pointing the semantically correct way, and scrollbar/overflow direction consistent with RTL -- then repeat the same check inside every modal, dropdown, and third-party embed to confirm `dir` inheritance held throughout the component tree, not just at the root.
