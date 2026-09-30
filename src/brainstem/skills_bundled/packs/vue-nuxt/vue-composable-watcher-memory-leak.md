---
name: vue-composable-watcher-memory-leak
description: Fix a Vue composable that accumulates watchers, listeners, or timers each time it is used, slowing the app over a session.
triggers: ["composable memory leak vue", "listeners piling up spa", "watcher count keeps growing", "onUnmounted not called composable", "vue app slows down over time"]
permissions: ["READ"]
---

## Symptom
An app that stays open for a while (navigating around a SPA without full
page reloads) gets progressively slower, or the same action starts
firing its handler multiple times -- and the common factor is a shared
composable used by many components, not any single component's own code.

## Likely causes
1. **The composable sets up a `watch`/`watchEffect`, a global event
   listener, a WebSocket subscription, or a `setInterval`, but never
   calls the returned stop handle or registers cleanup** -- because it's
   a plain function, not a component, it's easy to forget that cleanup is
   still required.
2. **The composable is called conditionally or inside a dynamic list**
   (e.g. once per item in a `v-for`), creating one watcher/listener per
   invocation without a matching teardown when an item is removed.
3. **Cleanup is registered with `onUnmounted`, but the composable is
   invoked outside a component's synchronous `setup()`** -- e.g. inside an
   async callback or inside an event handler -- so Vue can't associate the
   lifecycle hook with the calling component, and it silently does
   nothing (usually with an easy-to-miss dev warning).
4. **A composable intended as a module-level singleton (one listener for
   the app's whole lifetime) is instead invoked fresh from every
   component that uses it**, unintentionally multiplying identical
   listeners instead of sharing one.

## Diagnose
- In browser devtools, open the Elements/Event Listeners panel on
  `window`/`document`, mount and unmount the consuming component several
  times, and watch whether the listener count returns to baseline or
  keeps climbing.
- Temporarily add `{ onTrigger(e) { console.log(e) } }` to a suspected
  `watch`/`watchEffect` to confirm whether multiple, redundant instances
  are firing for what should be a single logical watcher.
- Check whether `onUnmounted` is called synchronously during the
  composable's own top-level execution (not inside a `.then()`, a
  `setTimeout`, or an event handler) -- that placement determines whether
  Vue can wire it up at all.

## Fix
Capture the `stop` function returned by `watch`/`watchEffect` and call it
from `onUnmounted` inside the composable itself, so every caller gets
cleanup for free without needing to remember it. Mirror every
`addEventListener` with a matching `removeEventListener` in `onUnmounted`
using the exact same handler reference. Keep the composable's setup call
synchronous within a component's `setup()`/`<script setup>` so
`onUnmounted` can register correctly; if it must be created outside that
context, use an explicit `effectScope()` tied to whatever owns its
lifetime instead of relying on implicit component association.

## Pitfalls
Approximating cleanup with a manual `isActive` flag checked inside the
callback (instead of actually calling `stop()`/`removeEventListener`)
silences the symptom -- the callback stops doing anything -- but the
underlying subscription, timer, or socket connection is still alive and
still consuming resources.

## Verify
Mount and unmount the consuming component repeatedly (or navigate to and
from the page several times) and confirm, via the devtools listener
count or a manual counter incremented on setup and decremented on
cleanup, that it returns to the same baseline after each cycle instead of
climbing.
