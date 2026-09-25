---
name: cls-async-content-swap-no-placeholder
description: Fix layout shift when first-party data fetched after initial render replaces a loading skeleton with content of different dimensions.
triggers: ["skeleton loader causes shift", "content jumps after data loads", "CLS after API call", "loading placeholder wrong size", "layout shift on data fetch"]
permissions: ["READ"]
---

## Symptom
CLS is flagged specifically for a region of the page that starts as a
loading skeleton or spinner and is later replaced by real, client-fetched
data (a personalized recommendation row, a comment count, a "You have N
notifications" banner) -- the surrounding content visibly jumps once the
data arrives, distinct from third-party embeds because this is the site's
own async UI, not an external script.

## Likely causes
1. **The skeleton/placeholder has different dimensions than the eventual
   real content** (e.g. a fixed 2-line skeleton but real content sometimes
   renders 3-4 lines), so swapping causes reflow whenever content doesn't
   match the assumed size.
2. **No placeholder exists at all** -- the component renders `null` while
   loading and then mounts the real content, so the space genuinely didn't
   exist before and gets inserted, pushing everything after it.
3. **The number of items is unknown until the fetch resolves** (e.g. "3
   related products" vs "8 related products"), so even a well-sized
   skeleton for one item can't account for a variable-length list.
4. **A conditional banner/notice renders only when a condition from the
   fetched data is true** (e.g. "your trial expires soon"), appearing
   above other content after the data loads instead of before.

## Diagnose
- In DevTools > Performance, record the trace through the client-side data
  fetch and find the Layout Shift entry timestamp; correlate it with the
  Network request for the API call to confirm this specific fetch is the
  cause (versus fonts or ads).
- Compare the skeleton component's rendered `getBoundingClientRect()`
  height against the real content component's height for representative
  data (median case and edge cases like empty state, max-length state).
- Check whether the component conditionally renders nothing (`{data &&
  <Banner/>}`) versus always rendering a reserved container -- inspect the
  DOM before and after the fetch resolves via DevTools Elements.

## Fix
Make the loading state occupy the same layout footprint as the most likely
real content, rather than treating the skeleton as a purely visual
stand-in -- the browser doesn't care that it "looks like" a placeholder,
only that its box size doesn't change size when swapped. Concretely: size
skeletons to match the *typical* real content height (using historical
data on average item count/text length, not an arbitrary guess), and for
variable-length lists, reserve space for the typical count and let genuine
outliers scroll or truncate rather than resize; always render the
container for conditional banners (even as a zero-visual-height but
already-present block using `visibility: hidden` sizing tricks, or fetch
the condition server-side so its presence is known before first paint);
and where feasible, fetch the data needed to size the component correctly
during SSR/initial load instead of purely client-side, eliminating the
swap altogether.

## Pitfalls
- Sizing the skeleton to the *maximum* possible content height to
  guarantee no shift creates a different problem -- excess empty space
  during loading that looks broken and hurts perceived performance for
  the common case.
- Using `min-height` on the container but not `height`, when the real
  content can be *shorter* than the skeleton, still shows a shift (just
  shrinking instead of growing) -- account for both directions.
- Solving this by delaying the whole page's first paint until the async
  data resolves trades CLS for worse LCP/FCP -- prefer reserving space
  over blocking render.

## Verify
Force the API call to resolve with representative data variations
(shortest, typical, longest) in a local/staging environment, and confirm
via DevTools Performance that no Layout Shift entries fire for the
region across all variations, then confirm the page's CLS in
Lighthouse/CrUX field data.
