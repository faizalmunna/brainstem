---
name: css-transition-not-firing-on-class-toggle
description: Fix a CSS transition or animation that silently doesn't play when a class is toggled via JavaScript, jumping straight to the end state instead.
triggers: ["css transition not working", "transition doesn't animate", "adding class doesn't animate", "animation jumps instantly instead of transitioning", "transition works on hover but not on class add"]
permissions: ["READ"]
---

## Symptom
A `transition` is defined on an element's CSS, and adding/removing a
class via JavaScript is supposed to animate a property (opacity, height,
transform) smoothly, but instead the element jumps instantly to the end
state with no visible animation -- even though the exact same transition
works fine on a `:hover` pseudo-class on the same element.

## Likely causes
1. **The class is added immediately after the element is inserted into
   the DOM in the same synchronous tick** (e.g. `el.classList.add('open')`
   right after `appendChild`), so the browser never paints the initial
   (pre-class) state -- there's nothing for the browser to interpolate
   *from*, so it renders straight to the final state on the first paint.
2. **The property being transitioned is changing from/to `display: none`**
   -- `display` is not animatable, and a property transitioning while an
   ancestor or the element itself flips `display: none` to `block` has no
   starting frame to transition from (the element didn't exist in a
   render-able state a moment earlier).
3. **The transitioned property's starting value is `auto`** (most common
   with `height`/`width`/`grid-template-rows: auto` used for
   accordion-style expand/collapse) -- `auto` is not interpolable, so the
   browser can't animate between a numeric end value and an `auto` start
   value.
4. **The `transition` property itself is only defined on `:hover` or a
   more specific selector than the class being toggled**, so the base
   element being animated via class toggle simply has no `transition`
   rule active for that state change at all.
5. **A conflicting later style (higher specificity, or `!important`)
   overrides the transitioned property immediately**, so the computed
   value changes in the same frame with no interpolation window, which
   looks identical to "the transition didn't fire" even though the CSS
   rule is technically present.

## Diagnose
- In DevTools' Elements panel, toggle the class manually via the class
  list checkbox UI (not via re-running the JS) and watch whether the
  transition plays -- if it does play this way but not via the app's own
  JS, the bug is in *when* JS adds the class relative to paint timing.
- Check the Animations panel in Chrome DevTools -- it records fired CSS
  transitions/animations; if nothing appears when the class is toggled
  through the app, the transition truly never started (as opposed to
  playing too fast to notice).
- Check computed `transition` property on the element in both its
  before- and after-class states -- if it's only present in one state,
  the selector scoping is the issue (cause 4).
- For height/width accordion cases, check whether the "closed" state uses
  `height: 0` and the "open" state uses `height: auto` -- that mismatch is
  the direct culprit for cause 3.

## Fix
For the paint-timing issue, force a reflow (or use `requestAnimationFrame`
twice, or the `element.offsetHeight` read trick) between setting the
initial state and adding the class that triggers the end state, so the
browser actually paints the starting frame before the transition begins;
many frameworks solve this by adding the class one frame after mount
rather than synchronously. For `display: none` transitions, animate
`opacity`/`transform` and switch `display` at the *end* of the transition
via the `transitionend` event (or use the newer `transition-behavior:
allow-discrete` with `@starting-style` in browsers that support it) rather
than flipping `display` and the animated property in the same step. For
`auto`-height accordions, either transition `grid-template-rows` from `0fr`
to `1fr` on a CSS grid wrapper (which *is* interpolable, unlike `height:
auto`), or measure the element's `scrollHeight` in JS and transition to
that explicit pixel value instead of `auto`. Move the `transition`
declaration onto the base selector (not just `:hover`) so it applies
across every state the class toggle produces.

## Pitfalls
- Wrapping every class toggle in a double `requestAnimationFrame` as a
  blanket fix adds a visible one-frame delay to state changes that didn't
  need it and can make simple toggles feel sluggish -- apply the reflow
  trick only where the initial-paint problem is actually confirmed.
- The `grid-template-rows: 0fr` to `1fr` accordion trick requires the
  animated content to be wrapped in an extra grid item with
  `overflow: hidden` and `min-height: 0`; skipping the wrapper (animating
  the content's own grid-template-rows directly) often silently fails to
  clip the content during the collapse phase.

## Verify
Open the Chrome DevTools Animations panel, trigger the class toggle
through the actual application flow (not by hand in DevTools), and
confirm a transition/animation entry appears with a duration matching the
CSS and that the visual change plays over that duration rather than
happening in a single frame.
