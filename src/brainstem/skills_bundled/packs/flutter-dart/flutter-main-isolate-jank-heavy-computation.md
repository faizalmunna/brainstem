---
name: flutter-main-isolate-jank-heavy-computation
description: Diagnose UI jank from heavy synchronous computation blocking the main isolate despite being wrapped in async code.
triggers: ["ui freezes during json parsing flutter", "app janks on heavy computation", "async function still blocks ui flutter", "compute vs isolate flutter jank"]
permissions: ["READ"]
---

## Symptom
The UI freezes or stutters -- dropped frames, unresponsive taps, a
spinner that stops animating -- for a noticeable duration whenever a
specific action runs, such as parsing a large JSON response, decoding a
large image, sorting/filtering a big in-memory list, or computing a
hash, even though the surrounding code is `async`/awaited.

## Likely causes
1. **`async`/`await` alone doesn't move CPU-bound work off the main
   isolate** -- `await` only yields at I/O boundaries; a synchronous,
   CPU-heavy function called inside an async method still runs entirely
   on the UI isolate and blocks frame rendering for its whole duration.
2. **Large JSON decoding** (`jsonDecode` on a multi-megabyte payload) or
   image decoding running on the main isolate -- a classic case of
   "looks async because it's inside an async function" while actually
   being synchronous CPU work blocking the event loop.
3. **A `Timer`/`Future.delayed` used to "chunk" heavy work** into smaller
   synchronous pieces, but each chunk still exceeds a frame budget
   (~16ms at 60Hz), so jank persists, just spread across more frames.
4. **Heavy work correctly moved to `compute()`/an isolate, but the data
   passed across the boundary is itself large**, shifting rather than
   fixing the bottleneck into isolate message-passing/serialization
   overhead.

## Diagnose
- Record a DevTools CPU Profiler session while triggering the janky
  action and check whether the flame chart shows the heavy function
  executing directly under the UI isolate's frame callbacks (confirming
  it blocks the main isolate) versus already running elsewhere.
- Check the Performance Overlay -- a single very tall red UI-thread frame
  bar exactly at the moment of the action (rather than a sustained series
  of moderately red bars) points to one big synchronous blocking call.
- Time the suspect function directly with a `Stopwatch` around just that
  call to quantify its actual synchronous duration, independent of any
  surrounding async wrapper.
- Grep for `jsonDecode`, manual parsing loops, image processing, or
  sorting/filtering over large collections running inside otherwise-async
  methods without `compute()`/`Isolate.run()`.

## Fix
- Move genuinely CPU-bound work to a separate isolate via `compute()`
  (for a simple top-level function) or `Isolate.run()` (supports
  closures), so the main isolate's event loop and frame scheduling stay
  free while the work happens in parallel.
- For JSON specifically, decode on a background isolate via
  `compute(jsonDecode, jsonString)`, or use a streaming/incremental
  parser for very large payloads so parsing doesn't require one giant
  synchronous pass.
- If work must stay on the main isolate (e.g. it needs direct access to
  widget-bound state that isn't isolate-transferable), break it into
  smaller synchronous chunks yielded via `Future.microtask` or
  `Future.delayed(Duration.zero)` between chunks, understanding this
  trades total wall-clock time for smoothness rather than eliminating
  the cost.
- When isolate message-passing itself becomes the bottleneck, transfer
  only the fields actually needed, or use `TransferableTypedData` for
  large binary payloads, rather than serializing an entire large object
  graph both ways.

## Pitfalls
- Wrapping a call in `Future(() => heavyWork())` or `Future.microtask`
  and assuming that "made it async" -- these still run on the same
  isolate/event loop as the UI; only `compute()`/`Isolate.run()`/
  `Isolate.spawn` actually move work to a different isolate.
- Moving a genuinely fast operation (a few milliseconds) to `compute()`
  adds isolate spawn and serialization overhead that can make it slower
  overall -- profile first to confirm the operation is expensive enough
  (generally well over a frame budget) to be worth isolating.

## Verify
Re-run the DevTools CPU Profiler/Performance Overlay during the same
action and confirm the heavy function's execution now shows on a
separate isolate track rather than blocking the main isolate's frame
callbacks, and that UI-thread frame bars stay under the jank threshold
throughout the operation, with the UI remaining responsive (e.g. a
running animation keeps animating) while the work completes.
