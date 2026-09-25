---
name: large-image-android-oom-crash
description: Fix an Android-only out-of-memory crash caused by loading large or numerous images without downscaling or recycling.
triggers: ["android oom crash loading images", "outofmemoryerror bitmap too large", "app crashes scrolling through photos android", "image gallery crashes on android only", "bitmap allocation failed react native"]
permissions: ["READ"]
---

## Symptom
The app crashes on Android (but not iOS) when displaying a screen with
many images, high-resolution photos, or a photo gallery/carousel --
typically with a native crash log mentioning `OutOfMemoryError`,
`Bitmap too large`, or `Failed to allocate a ... byte allocation`, and
the crash gets worse or more frequent on lower-RAM Android devices while
the equivalent iOS build handles the same content fine.

## Likely causes
1. **Full-resolution images decoded at their source size regardless of
   display size** -- a 12MP camera photo displayed in a 100x100 thumbnail
   still gets decoded to a full-resolution bitmap in memory by default
   unless the image pipeline is told to downsample, and Android's
   per-app bitmap memory ceiling is hit much sooner than iOS's more
   generous default handling for the same content.
2. **No image recycling/caching strategy in a scrollable list of
   images** -- as a `FlatList`/`ScrollView` of images scrolls, each new
   image decode adds to memory without previous off-screen ones being
   released, especially with `Image`'s default (non-caching, non-
   recycling) behavior for remote images.
3. **Multiple full-size copies of the same image held simultaneously** --
   e.g. a thumbnail grid and a full-screen preview both independently
   decoding the same source image at different sizes rather than sharing
   a decoded/cached version, doubling memory for content that's
   logically the same asset.
4. **Android's stricter per-app heap limits being hit sooner on devices
   with `largeHeap` not enabled**, or even with it enabled, an app
   genuinely needing more memory than is reasonable for the device class
   because of the above issues compounding.
5. **GIF/animated image or very large local asset bundling** -- a large
   local image asset bundled at full resolution and referenced via
   `require()`, or an animated GIF library that keeps every decoded frame
   in memory simultaneously, can exhaust memory on its own even without a
   scrollable list involved.

## Diagnose
- Reproduce on a lower-RAM or older Android device/emulator (crashes tied
  to memory ceilings often don't reproduce on a high-end flagship test
  device), and pull the crash log via `adb logcat` immediately after --
  it typically names the bitmap allocation size that failed.
- Use Android Studio's Profiler (Memory tab) while scrolling through the
  affected image list and watch for a steadily climbing native/graphics
  memory count that doesn't drop as images scroll off-screen.
- Check the actual dimensions of source images being loaded (log
  `Image.getSize()` or inspect the network response) against their
  rendered display dimensions -- a large gap (e.g. a 4000x3000 source
  rendered at 120x120) confirms unnecessary full-resolution decoding.
- Check whether `android:largeHeap="true"` is set in
  `AndroidManifest.xml` and whether the crash persists even with it
  enabled, which indicates the real fix is reducing memory use, not
  raising the ceiling.

## Fix
- Use an image component that supports server-side or client-side
  resizing to the actual display size (`expo-image`,
  `react-native-fast-image`, or a CDN/image-service URL parameter for
  width/height/quality) so images are decoded close to their rendered
  size rather than their source size.
- Ensure the image component used in scrollable lists actually recycles/
  releases off-screen bitmaps -- caching libraries built for this
  (disk+memory LRU caches) handle this far better than the bare `Image`
  component's default behavior for large remote image sets.
- Deduplicate decode work for the same logical image shown at multiple
  sizes by using a caching layer keyed on URL so the thumbnail and full-
  screen views can share a cache rather than each independently fetching
  and decoding full-resolution copies.
- For large local/bundled assets, pre-resize them to the actual maximum
  display size needed at build time rather than shipping and decoding
  full-resolution originals; for animated GIFs, consider a video format
  or a library designed for frame-efficient playback instead of a naive
  all-frames-in-memory GIF decoder.
- Enable `android:largeHeap="true"` only as a stopgap while the actual
  memory usage is being fixed, not as the permanent solution, since it
  raises the ceiling without addressing the underlying over-allocation.

## Pitfalls
- Relying on `android:largeHeap="true"` alone "fixes" the crash on
  higher-RAM devices while leaving it unresolved (or making it worse
  system-wide, since a large-heap app is a more aggressive target for the
  OS to kill under memory pressure) on the very low-RAM devices where it
  was most visible.
- Resizing images client-side after a full-resolution download still
  pays the network and initial-decode cost before resizing -- for
  remote images, request an appropriately-sized version from the source/
  CDN when possible rather than only resizing post-download.

## Verify
On a lower-RAM Android device or an emulator configured with a
constrained heap, scroll through the full image gallery/list end to end
multiple times while watching Android Studio's Profiler memory graph,
confirming memory stays roughly flat (not steadily climbing) and no
`OutOfMemoryError` crash occurs -- and confirm image quality at actual
display size is still visually acceptable after any downscaling applied.
