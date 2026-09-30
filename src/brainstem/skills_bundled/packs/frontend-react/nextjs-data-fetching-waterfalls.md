---
name: nextjs-data-fetching-waterfalls
description: Diagnose and fix sequential (waterfall) data fetching in Next.js App Router that makes pages load slower than the data dependencies actually require.
triggers: ["data fetching waterfall", "page loads slowly nextjs", "sequential fetches", "requests waterfall", "slow ttfb nextjs", "nested fetch slow"]
permissions: ["READ"]
---

## Symptom
A page takes noticeably longer to render than the slowest individual data
source should require; the network tab (or server timing) shows requests
firing one after another rather than in parallel, often nested inside
each other across Server Components.

## Likely causes
1. **A child Server Component fetches its own data only after its parent
   has finished fetching and rendering**, even though the child's fetch
   doesn't actually depend on the parent's data -- the nesting creates an
   artificial dependency.
2. **`await`ing fetches sequentially in one component** (`const a = await
   fetchA(); const b = await fetchB();`) when `b` doesn't depend on `a`.
3. **No `Suspense` boundaries**, so the whole page (or a whole large
   section) waits for the slowest fetch before anything streams to the
   client, instead of showing fast parts immediately and streaming in
   slow parts.
4. **Fetching the same data multiple times** in different components
   without relying on Next's fetch memoization/dedup, adding redundant
   round trips that appear as a waterfall of near-identical requests.

## Diagnose
- Use the Network tab (or Next.js's own request timing in dev mode) to
  see whether independent data sources are firing in parallel or one
  after another.
- For component-tree waterfalls, check whether a child component's data
  fetch is written to only run after receiving a prop from its parent
  when it could instead run independently and be composed with
  `Suspense`.
- Grep for sequential `await` calls in the same async component/function
  and check whether the second call actually needs the first call's
  result.

## Fix
- Kick off independent fetches concurrently with `Promise.all` (or by
  simply not `await`ing until both are needed) instead of awaiting them
  one after another.
- Push data fetching down into the components that need it and wrap slow
  sections in `<Suspense fallback={...}>` so fast content streams
  immediately and slow content streams in when ready, rather than
  blocking the whole page on the slowest source.
- Rely on Next's automatic fetch request memoization within a single
  render pass (same URL + options) instead of manually passing fetched
  data through many prop layers, and confirm caching options (`cache`,
  `next: { revalidate }`) are set intentionally rather than left at
  surprising defaults.
- For a genuinely dependent chain (`b` needs a value from `a`), that's a
  real waterfall, not a bug -- the fix there is either restructuring the
  API so both can be fetched from the parent's known inputs, or accepting
  the latency and using `Suspense` to at least not block unrelated parts
  of the page on it.

## Pitfalls
- Wrapping everything in `Promise.all` blindly, including fetches that
  really are dependent, produces incorrect behavior (using `undefined`
  before it's ready) rather than a speedup -- confirm independence before
  parallelizing.
- Adding `Suspense` boundaries without also handling the loading UI
  thoughtfully can make a page feel janky (multiple popping-in sections)
  even though it's technically faster by time-to-first-byte -- pair the
  fix with a deliberate loading-skeleton design, not just correctness.

## Verify
Compare the request waterfall (Network tab) before and after: independent
fetches should now start at roughly the same time rather than one
starting only after the previous one resolves, and overall time-to-
interactive should drop by roughly the difference between the sum and the
max of the independent fetch durations.
