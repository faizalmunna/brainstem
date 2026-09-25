---
name: skip-link-missing-or-broken
description: Fix a missing or non-functional "skip to content" link that forces keyboard users to tab through the entire navigation on every page.
triggers: ["skip to content link not working", "no skip link", "keyboard users tab through whole nav", "skip navigation link broken", "skip link doesn't move focus"]
permissions: ["READ"]
---

## Symptom
A keyboard-only user landing on any page (especially after following a
link from search results or another site) must press Tab dozens of
times through the header, logo, primary nav, and sometimes a secondary
nav before reaching the main content -- on every single page load,
because browsers don't remember tab position across navigations. Either
there's no skip link at all, or one exists but pressing Enter on it
doesn't visibly move focus anywhere (it appears to do nothing, or jumps
the visual scroll position without moving actual keyboard focus).

## Likely causes
1. **No skip link exists in the markup at all** -- it was never added,
   or was present in an older template and dropped during a redesign
   that rebuilt the header component.
2. **The skip link targets an anchor that doesn't exist or was
   renamed** -- `href="#main-content"` but the main landmark's `id` was
   changed to `main` or removed entirely during a refactor, so the
   browser has nothing to jump to.
3. **The target element isn't focusable**, so even though the browser
   scrolls to the anchor, actual keyboard focus doesn't move there --
   pressing Tab again continues from wherever focus previously was
   (often back at the top), not from the target. A plain `<main
   id="main-content">` with no `tabindex` is not focusable by default.
4. **The skip link is visually hidden with `display: none` or
   `visibility: hidden`** instead of the standard "visually hidden until
   focused" pattern, which removes it from the tab order entirely --
   keyboard users can never reach it even though it exists in the DOM.

## Diagnose
- Load any page, press Tab once as the very first action, and check
  whether a skip link appears (visually, when it receives focus) -- if
  nothing appears, either it's absent or hidden in a way that also
  removes it from the tab order.
- Inspect the skip link's `href` and confirm an element with a matching
  `id` exists elsewhere in the current page's DOM.
- Activate the skip link with Enter, then immediately press Tab again --
  the next focused element should be the first interactive element
  *inside* main content, not back at the top of the nav. If it returns
  to the nav, the target never actually received focus.
- Check the target element's computed `tabindex` in devtools -- native
  landmarks like `<main>` need `tabindex="-1"` added to become
  programmatically focusable (without adding them to the normal tab
  order).

## Fix
Add a skip link as the very first focusable element in the DOM,
visually hidden by default but shown when it receives keyboard focus
(the standard `.sr-only` combined with a `:focus` override that
restores visibility/position, not `display:none`/`visibility:hidden`
which would remove it from the tab order). Point its `href` at the
`id` of the main content landmark, and give that landmark `tabindex=
"-1"` so it becomes focusable via script/anchor navigation without
joining the normal Tab sequence (it should still not be reachable by
plain Tabbing from elsewhere). If the framework's anchor-jump doesn't
reliably move focus (some SPA routers intercept hash changes), call
`.focus()` on the target element explicitly in the skip link's click/
activation handler rather than relying on default browser anchor
behavior alone.

## Pitfalls
- Adding `tabindex="-1"` to the main landmark but forgetting the CSS
  `:focus` visibility override on the skip link itself means the link
  now technically works but is invisible when focused, so sighted
  keyboard users can't see where focus is or confirm the skip worked.
- Using `tabindex="0"` instead of `-1"` on the main content target adds
  an extra, confusing stop in the normal tab order for every user, not
  just those who used the skip link.
- Implementing the skip link as a JavaScript `scrollIntoView()` call
  without also moving actual focus fixes the visual jump but leaves
  keyboard focus behind, so the very next Tab press continues from the
  old position instead of from main content.

## Verify
Load the page fresh, press Tab once to reveal the skip link, press
Enter, then press Tab again and confirm the next focused element is the
first interactive control inside the main content region -- not back in
the header or navigation.
