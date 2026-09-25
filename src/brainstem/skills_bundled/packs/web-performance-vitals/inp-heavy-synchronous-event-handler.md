---
name: inp-heavy-synchronous-event-handler
description: Fix a poor INP score where clicking a button or typing in a field feels janky because a synchronous handler blocks the main thread before the next paint.
triggers: ["INP is bad", "click feels laggy", "button click is unresponsive", "interaction to next paint high", "clicking feels delayed"]
permissions: ["READ"]
---

## Symptom
Chrome's INP (Interaction to Next Paint) metric is flagged poor (>200ms)
for a specific interaction -- a button click, a dropdown open, or typing a
character -- and users describe it as "the page freezes for a moment" or
"my click doesn't register right away."

## Likely causes
1. **The event handler itself does synchronous, expensive work** (sorting
   a large array, running a regex over a big string, synchronous JSON
   parsing/stringifying, DOM measurement in a loop) before the UI can
   update.
2. **The handler triggers a synchronous state update that causes a large
   re-render**, and the re-render's cost (not the handler's own logic) is
   what's blocking the next paint.
3. **Forced synchronous layout ("layout thrashing")** -- reading a layout
   property (`offsetHeight`, `getBoundingClientRect`) right after writing
   to the DOM, inside the handler, forcing the browser to recalculate
   layout synchronously mid-script instead of batching it.
4. **A third-party script's event listener runs on the same interaction**
   (e.g. an analytics click tracker attached to the same element or a
   delegated listener on `document`), adding blocking work you don't
   directly control but that still counts against your INP.
5. **The interaction fires during an unrelated long task already running**
   (e.g. a big hydration or data-processing task from page load still
   occupying the main thread when the user clicks).

## Diagnose
- Record a Chrome DevTools Performance trace, perform the slow interaction,
  and look at the "Interactions" track -- it breaks INP into Input Delay,
  Processing Time, and Presentation Delay; identify which phase dominates.
- If Processing Time dominates, expand the main thread flame chart under
  the interaction and find the specific long task/function consuming most
  of the time (look for wide yellow/purple blocks).
- Use `PerformanceObserver` with `type: 'event'` and `durationThreshold`
  in production (via web-vitals library's `onINP` with attribution build)
  to capture real-user INP culprits, since local testing may not reproduce
  the exact data size/device conditions users hit.
- Check the Elements/Sources call stack at the point of the long task to
  confirm whether it's your handler, a re-render, or a third-party script.

## Fix
The core pattern is to get *something* painted before doing the expensive
work, and to break up whatever can't be avoided so it doesn't occupy the
main thread in one uninterrupted block. Concretely: move expensive,
non-visual work (sorting, parsing, heavy computation) off the critical
path with `setTimeout(fn, 0)`, `requestIdleCallback`, or a Web Worker so
the browser can paint the immediate visual feedback (button pressed state,
spinner) first; for large re-renders, use `startTransition`/deferred
updates (React) or otherwise separate the urgent visual update from the
non-urgent data update so the framework can paint the cheap part first;
batch DOM reads and writes separately (read all layout properties first,
then write) to avoid forced synchronous layout; and for unavoidably large
computations, chunk them into smaller pieces yielded across multiple
frames instead of one synchronous pass.

## Pitfalls
- Wrapping the *entire* handler in `setTimeout` just to "make it async"
  without actually reducing the work done just moves when the block
  happens, and can make the UI feel disconnected from the click if visual
  feedback isn't rendered first.
- Overusing Web Workers for state that the main thread needs immediately
  introduces message-passing latency and serialization cost that can
  offset the benefit for small payloads -- reserve workers for genuinely
  heavy, parallelizable work.
- Fixing the handler but ignoring a third-party script attached to the
  same element leaves INP bad even though your own code trace looks clean
  -- attribution data (cause 4) matters before declaring victory.

## Verify
Re-run the same interaction in a DevTools Performance recording and
confirm Processing Time in the Interactions track dropped, and check the
Chrome UX Report / real-user `web-vitals` INP value for that page/element
over the following days to confirm the improvement holds under real
traffic and device variety, not just on your dev machine.
