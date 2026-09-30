---
name: ios-safari-viewport-height-bug
description: Fix a full-height layout using vh units that overflows or leaves a gap specifically on iOS Safari due to dynamic browser chrome.
triggers: ["100vh too tall on iphone", "layout broken only on iOS Safari", "content cut off on mobile safari", "vh units wrong on iphone", "bottom bar covers content on iOS"]
permissions: ["READ"]
---

## Symptom
A layout that uses `height: 100vh` (a full-screen hero, a fixed-position
footer, a mobile app-style single-screen view) looks correct on desktop
and on Android Chrome, but on iOS Safari specifically the content either
overflows past the visible area (gets covered by the address bar/bottom
toolbar) or leaves an unexpected gap that changes size as the user
scrolls, particularly when the browser chrome shows/hides.

## Likely causes
1. **`100vh` in Safari on iOS is defined against the *largest* possible
   viewport** (as if the address bar and bottom toolbar were both fully
   collapsed), not the currently visible viewport -- so a `100vh`
   element is taller than what's actually visible when the browser chrome
   is showing, pushing content below the fold or under the toolbar.
2. **The viewport height changes dynamically as the user scrolls**
   (Safari's chrome auto-hides/shows), so any layout computed once from
   `100vh` at page load becomes wrong the moment the toolbar state
   changes, unlike a static desktop viewport.
3. **A `position: fixed` element anchored with `bottom: 0`** gets pushed
   around or hidden behind the dynamic bottom toolbar specifically, since
   `fixed` positioning interacts with iOS Safari's chrome differently
   than a simple height calculation would suggest.
4. **JavaScript `window.innerHeight` is read once on load and cached**
   (a common workaround for old `vh` bugs) but never updated on the
   `resize`/`visualViewport` events that fire when Safari's chrome
   changes, so the cached value goes stale as soon as the user scrolls or
   rotates the device.

## Diagnose
- Reproduce on an actual iOS device or Safari's iOS Simulator (Chrome
  DevTools' device emulation does not reproduce this bug accurately,
  since it only emulates viewport dimensions, not Safari's dynamic
  chrome behavior) -- scroll down slightly to trigger the toolbar
  collapsing and watch whether the layout shifts or content becomes newly
  visible/hidden.
- Check whether the broken element uses `100vh` directly in CSS, or a
  JS-computed height derived from a one-time `window.innerHeight` read,
  by searching the stylesheet and any layout JS for `vh` and
  `innerHeight`.
- Use Safari's own Web Inspector (via a Mac connected to the device, or
  the Simulator) to inspect computed height values before and after
  scrolling to confirm the element's height doesn't track the actual
  visible viewport.

## Fix
Replace `100vh` with the newer dynamic viewport units -- `100dvh` (dynamic
viewport height, which tracks the currently visible area as Safari's
chrome shows/hides) for elements that should always match visible space,
or `100svh`/`100lvh` (small/large viewport height) when a stable minimum
or maximum is specifically wanted instead of a dynamically resizing value.
Where broad browser support for `dvh` is a concern, use the
`window.visualViewport` API (not plain `resize`) to recompute a CSS custom
property (e.g. `--real-vh`) on the `visualViewport`'s `resize` and
`scroll` events, and reference that variable in place of `vh` in CSS --
`visualViewport` fires specifically when Safari's chrome changes, unlike
the main `resize` event.

## Pitfalls
- Switching every `100vh` in the codebase to `100dvh` without checking
  browser support requirements can regress older browsers that don't
  support dynamic viewport units at all -- pair it with a `100vh`
  fallback declared first, since CSS falls back to the last understood
  declaration.
- The `visualViewport` JS workaround, if only wired to `resize` and not
  also `scroll`, misses the specific case where Safari's toolbar
  collapses purely from scrolling without a viewport resize event firing
  -- listen to both.

## Verify
On an actual iOS Safari session (device or Simulator), scroll to trigger
the toolbar's collapse/expand and confirm the layout's height adjusts to
match the currently visible viewport with no content hidden behind the
toolbar and no unexpected gap appearing at any toolbar state.
