---
name: nuxt-page-transition-scroll-position
description: Fix scroll position resetting incorrectly or not restoring on back navigation after enabling Nuxt page transitions.
triggers: ["scroll position wrong after page transition", "nuxt page transition breaks scroll", "scroll not restored on back button nuxt", "page transition scroll jump", "scrollBehavior not working nuxt"]
permissions: ["READ"]
---

## Symptom
After enabling Nuxt page transitions (`pageTransition` / `app:transition`
CSS animations), navigating between routes leaves the new page scrolled
to wherever the previous page was instead of resetting to the top, or
using the browser back button no longer restores the scroll position it
used to.

## Likely causes
1. **The scroll reset runs before the page transition's leave animation
   actually finishes**, so it happens while the outgoing page is still
   visually present, making it look like nothing happened (or the
   incoming page appears to start pre-scrolled).
2. **A custom `scrollBehavior` in `app/router.options.ts`** returns
   `undefined`/nothing for a fresh navigation, or only handles the
   `savedPosition` (back/forward) case and forgets the "new navigation
   should go to top" case entirely.
3. **The transition wraps page content in a container with its own
   scroll context** (`overflow: auto` on a transition wrapper element),
   while the scroll-behavior logic only manipulates `window` scroll by
   default and never touches that inner scrolling element.
4. **Async data on the new page resolves after the transition and scroll
   reset already ran**, and the resulting layout shift (content
   populating in) moves the scroll position again afterward, looking like
   the reset "didn't stick."

## Diagnose
- Temporarily disable transitions (`definePageMeta({ pageTransition:
  false })`) and check whether scroll behavior is already correct without
  them -- if yes, the transition's timing is the cause, not the
  `scrollBehavior` config itself.
- Read the `scrollBehavior` function in `app/router.options.ts` line by
  line and check every code path returns something for both the
  `savedPosition` case and the plain-new-navigation case.
- Check `document.scrollingElement` versus any nested `div` with its own
  scrollbar during the broken transition, to confirm whether a custom
  scroll container (not `window`) is the one actually holding the wrong
  position.

## Fix
Implement `scrollBehavior` to explicitly return `{ top: 0 }` for fresh
navigations and `savedPosition` when it's present (back/forward), rather
than leaving either case to fall through to a default. If the transition
uses explicit JS hooks (`onAfterLeave`/`onEnter`), perform the scroll
reset there instead of relying purely on the router's own timing, so it
happens only after the outgoing page is actually gone from view. If a
custom scroll container is used instead of `window`, target that specific
element explicitly in the scroll-restoration logic.

## Pitfalls
Forcing `window.scrollTo(0, 0)` unconditionally in every page's
`onMounted` "fixes" the fresh-navigation case but fights the router's own
scroll restoration for legitimate back/forward navigation, breaking the
"return to where I was" behavior users expect when pressing back.

## Verify
Navigate forward through several pages and confirm each lands scrolled to
the top; then use the browser back button repeatedly and confirm scroll
position is restored to where it was on each previous page -- both
checks performed with the page transition still enabled, not with it
turned off.
