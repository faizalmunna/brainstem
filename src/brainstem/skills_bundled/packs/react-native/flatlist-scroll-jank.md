---
name: flatlist-scroll-jank
description: Diagnose a FlatList or SectionList that drops frames, stutters, or shows blank cells while the user scrolls a long list.
triggers: ["flatlist janky scroll", "list stutters when scrolling", "flatlist dropping frames", "blank cells while scrolling", "flatlist performance bad"]
permissions: ["READ"]
---

## Symptom
Scrolling a long `FlatList`/`SectionList` (typically hundreds+ rows, or rows
with images/complex layout) drops below 60fps, shows brief blank/white
cells while flying past them, or visibly stutters on fling -- especially
on mid-range Android devices, even though the same list feels fine with a
handful of items in dev.

## Likely causes
1. **Heavy or non-memoized `renderItem`** -- each row re-creates inline
   functions/objects and re-renders on every parent re-render (e.g. the
   list's parent re-renders on scroll-position state changes), so React
   is doing far more work per frame than the visible row count implies.
2. **Missing `keyExtractor`/unstable keys**, forcing React to remount cells
   instead of recycling them, which defeats `FlatList`'s cell-recycling
   entirely and makes every render as expensive as a first mount.
3. **Images without fixed dimensions or without a fast image cache**,
   causing layout thrash (rows resizing after image load) and repeated
   decode work as cells recycle past the same image URLs.
4. **`windowSize`/`initialNumToRender`/`maxToRenderPerBatch` left at
   defaults for an unusually heavy row**, so React Native tries to render
   more off-screen rows than the JS thread can keep up with between
   frames, or too few are pre-rendered and blank cells flash in during
   fast scrolls.
5. **Expensive work happening on the JS thread during scroll** (a
   `scroll` event handler doing synchronous computation, or `onScroll`
   without `scrollEventThrottle` tuned), competing with list rendering
   for the same thread.

## Diagnose
- Open the React DevTools Profiler (or add a `console.count` in
  `renderItem`) while scrolling and check how many times each row renders
  per second -- a row that isn't visible re-rendering at all is a red flag.
- Use the in-app Perf Monitor (shake menu -> Show Perf Monitor, or Flipper's
  React Native Performance plugin) to see the JS and UI thread FPS
  separately while scrolling -- JS FPS dropping but UI FPS holding (or
  vice versa) tells you which thread is the bottleneck.
- Temporarily replace `renderItem`'s content with a plain colored `View`
  of the same size -- if jank disappears, the row's render cost (not
  FlatList's virtualization) is the problem.
- Check whether `keyExtractor` is defined and returns a stable id, not
  `index` or a newly-created string per render.

## Fix
- Wrap the row component in `React.memo` and make sure `renderItem` (and
  any callbacks passed into it) are stable across renders -- via
  `useCallback` with the correct dependency array -- so recycled cells
  actually skip re-rendering when their data hasn't changed.
- Provide a real `keyExtractor` keyed on a stable data id so cell
  recycling works as designed, and pair it with `getItemLayout` when row
  height is fixed or computable, which lets `FlatList` skip a measurement
  pass entirely.
- Use a caching image component (e.g. `expo-image` or
  `react-native-fast-image`) with explicit `width`/`height` set, so decoded
  images are cached by URL and rows don't reflow after load.
- Tune `windowSize`, `maxToRenderPerBatch`, and `initialNumToRender` based
  on actual row cost measured above, rather than guessing -- for very
  heavy rows, `removeClippedSubviews` (Android) can also help by dropping
  native views for off-screen cells.
- For genuinely huge datasets, consider `FlashList` (from Shopify), which
  recycles views more aggressively than `FlatList` by design.

## Pitfalls
- Cranking `windowSize` up "to fix blank cells" without addressing row
  render cost just makes the JS thread render more expensive rows ahead
  of time, trading blank-cell flashes for worse overall fling performance.
- Wrapping every row in `React.memo` without stabilizing the props passed
  to it (a new inline object or arrow function per parent render) gives
  zero benefit -- `React.memo`'s shallow comparison sees a "new" prop
  every time and re-renders anyway.
- Switching to `FlashList` without providing an accurate `estimatedItemSize`
  can produce worse jank than `FlatList`, since its recycling strategy
  depends on that estimate being close to reality.

## Verify
With the Perf Monitor or Flipper's performance plugin open, fling the
list end to end and confirm JS and UI thread FPS both stay at or near
60fps (no sustained drops below ~50), and that no blank cells appear
during a fast fling on a mid-tier Android device or emulator throttled to
a lower CPU speed.
