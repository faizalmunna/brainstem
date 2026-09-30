---
name: flutter-listview-jank-missing-itemextent
description: Diagnose a ListView or GridView janking with large item counts due to missing itemExtent or lazy building.
triggers: ["listview scroll jank", "flutter list stutters with many items", "gridview dropping frames", "long list is laggy flutter"]
permissions: ["READ"]
---

## Symptom
Scrolling a list or grid with hundreds or thousands of items stutters and
drops frames -- visible as the Performance Overlay's UI-thread bar
turning red, or DevTools' frame chart showing frames well over the
16ms budget -- especially the first time the user scrolls into new
territory or when rows have irregular heights.

## Likely causes
1. **Using `ListView(children: [...])` with an explicit children list**
   instead of `ListView.builder`, which builds every item eagerly at
   construction time instead of lazily as it scrolls into view.
2. **No `itemExtent`/`prototypeItem` set for a uniform-height list**,
   forcing Flutter to lay out and measure each item individually just to
   estimate scroll offsets and total extent.
3. **Expensive work inside each item's `build()`** -- synchronous image
   decoding, string formatting, or nested unbounded layouts -- repeated
   every time an item scrolls back into the cache extent.
4. **Unsized/uncached images** (`Image.network`/`Image.asset` without
   `cacheWidth`/`cacheHeight` matched to display size) causing full-
   resolution decode cost on every build of that item.

## Diagnose
- Enable the Performance Overlay (`flutter run --profile`) and scroll --
  look for the top (UI) bar spiking above the red threshold line during
  scroll, not just during initial load.
- Record a DevTools CPU Profiler session while scrolling and check
  whether time is dominated by item layout/build, image decode, or
  paint.
- Check the list's construction: `ListView.builder`/`GridView.builder`
  vs. a hand-built children list, and whether `itemExtent`/`prototypeItem`
  is set for uniform rows.
- Use the widget inspector to count live item widgets while scrolled to
  the middle of a long list -- if the count is close to the total item
  count instead of visible-plus-cache-extent, lazy building isn't
  actually happening.

## Fix
- Switch to `ListView.builder`/`GridView.builder` (or `SliverList`/
  `SliverGrid` with a builder delegate) so only visible items plus a
  small cache extent are built at any time.
- Set `itemExtent` (or `prototypeItem`) whenever every row shares a fixed
  height -- this lets Flutter compute scroll metrics analytically instead
  of laying out every item, which is usually the single biggest win for
  long uniform lists.
- Move expensive per-item work out of `build()`: precompute formatted
  strings once, size images to their display dimensions via
  `cacheWidth`/`cacheHeight`, and reserve `AutomaticKeepAliveClientMixin`
  for items whose internal state must genuinely survive scrolling off-
  screen.
- For very large or open-ended datasets, paginate the underlying data
  source instead of materializing the whole list in memory up front.

## Pitfalls
- Applying `itemExtent` to a list whose rows actually vary in height
  causes silent clipping or overlapping content rather than an error --
  only use it when row height is genuinely fixed.
- Adding `RepaintBoundary`/`AutomaticKeepAliveClientMixin` to every item
  "just in case" defeats lazy disposal and inflates memory usage; reserve
  keep-alive for items that truly need to preserve state (video players,
  in-progress form fields) while off-screen.

## Verify
Re-enable the Performance Overlay and scroll rapidly through the entire
list: the UI-thread bar should stay under the frame-budget threshold
consistently, and the widget inspector's live item count should stay
roughly constant regardless of total list length rather than growing
with it.
