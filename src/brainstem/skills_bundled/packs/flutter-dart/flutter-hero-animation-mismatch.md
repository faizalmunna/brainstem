---
name: flutter-hero-animation-mismatch
description: Diagnose a Hero animation glitching or failing to trigger across a navigation transition between routes.
triggers: ["hero animation not working flutter", "hero widget jumps instead of animating", "hero transition flickers", "hero flight not triggering"]
permissions: ["READ"]
---

## Symptom
A `Hero` animation between two routes either doesn't animate at all (the
widget just jumps to its new position) or animates with a visible flash
or mismatch -- wrong size, wrong image, a flickering duplicate -- during
the transition.

## Likely causes
1. **The `tag` values on the two Hero widgets don't match exactly** --
   different strings, or an object used as the tag without a proper
   `==`/`hashCode` override -- so Flutter treats them as unrelated and
   simply swaps instantly instead of animating.
2. **The source and destination Heroes aren't under the same
   Navigator** -- one is inside a nested Navigator, a Dialog, or a
   separate `MaterialApp`/router scope -- so the Hero controller can't
   find a matching pair to fly between.
3. **The Hero's child differs significantly in type/aspect ratio between
   routes** (e.g. `Image.network` on one screen, a decorated `Container`
   on the other), producing a jarring visual flash mid-flight since the
   default flight animates bounds without smoothly morphing dissimilar
   content.
4. **The transition bypasses the default Hero flight wiring** -- a custom
   `PageRouteBuilder` that doesn't compose with the transitions delegate,
   or a modal (`showDialog`/`showModalBottomSheet`) not wired for flight
   -- or two navigations fire in quick succession and the Hero controller
   loses track of the flight.

## Diagnose
- Compare the exact `tag` value passed to both Hero widgets at a
  breakpoint or print statement right before navigation -- confirm they
  are `==`-equal, not just visually similar strings.
- Inspect both routes' widget trees in the Flutter Inspector to confirm
  both Heroes are descendants of the same Navigator, with no nested
  Navigator/Dialog boundary between them.
- Temporarily swap both Hero children for identical simple widgets (e.g.
  matching colored Containers) to isolate whether the animation mechanism
  works structurally versus the flash being a content-mismatch issue.
- Check the route-push code for a custom `PageRouteBuilder`/transition and
  confirm it isn't overriding the transition in a way that skips the
  default Hero flight shuttle builder.

## Fix
- Use a single stable identifier (an ID from the data model, not a list
  index or a freshly constructed object) as the Hero tag on both ends,
  ensured identical.
- Ensure both Heroes live under the same Navigator; restructure so both
  screens share the root Navigator, or accept that Hero can't span a
  genuine nested-Navigator boundary.
- If the two representations genuinely differ (thumbnail vs. full
  image), supply a custom `flightShuttleBuilder` to explicitly define
  what's shown mid-flight instead of letting Flutter default-morph two
  dissimilar children.
- Use the standard `Navigator.push`/`MaterialPageRoute` (or a
  `PageRouteBuilder` that still composes with `HeroController`) rather
  than a fully custom transition that bypasses Hero flight wiring, unless
  a custom `flightShuttleBuilder` is explicitly provided.

## Pitfalls
- Using a list index as the Hero tag works until the list is
  filtered/sorted/reordered, at which point the wrong items animate
  together -- always tag by stable identity, not position.
- Adding a `flightShuttleBuilder` to fix the flash but only handling
  `HeroFlightDirection.push` can fix the forward transition while
  leaving the pop transition still flashing -- test both directions.

## Verify
Trigger the navigation both forward and via back-navigation multiple
times, and visually confirm (or record a screen capture, since this is
inherently a visual/timing check) the Hero widget smoothly animates
position and size across the transition with no jump-cut or flash in
either direction.
