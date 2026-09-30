---
name: elasticsearch-deep-pagination-performance-collapse
description: Requesting deep pages with from plus size causes severe latency and memory spikes instead of using search_after or a point in time.
triggers: ["deep pagination elasticsearch slow", "Result window is too large", "from and size performance", "page 500 of search results slow", "search_after vs scroll", "pagination timeout elasticsearch"]
permissions: ["READ"]
---

## Symptom
Pagination works fine for the first several pages of search results, then
either fails outright with `Result window is too large, from + size must
be less than or equal to: [10000]`, or succeeds but with rapidly
increasing latency and coordinating-node memory usage as users (or a
scraper/export job) page deeper into results.

## Likely causes
1. **`from`+`size` pagination fundamentally requires each shard to
   compute and sort `from + size` results, then the coordinating node
   merges all shards' results and discards everything before `from`** --
   so requesting page 500 at 20 results/page means every shard sorts and
   returns 10,020 documents' worth of scoring data, of which only 20 are
   actually used, and this cost grows with page depth, not page size.
2. **A UI or API genuinely allows arbitrarily deep pagination** (e.g. "go
   to page N" or an unbounded offset parameter) when the actual user need
   is either "browse forward through results" (well served by
   `search_after`) or "export/paginate through everything" (well served
   by the scroll API or a Point-in-Time with `search_after`), neither of
   which requires deep `from` at all.
3. **A batch export or sync job uses `from`+`size` in a loop** to walk an
   entire index, hitting the `index.max_result_window` ceiling (default
   10,000) and either failing or being worked around by raising that
   setting, which fixes the error but not the underlying per-request cost.
4. **`index.max_result_window` was raised to paper over the error**
   without changing the access pattern, which removes the safety limit
   but keeps the same quadratic-ish per-shard cost, making deep pages
   slow rather than rejected.

## Diagnose
- Check application/API logs or the query itself for `from` values in the
  hundreds or thousands -- this alone confirms the deep-pagination
  pattern regardless of whether an error has surfaced yet.
- If `Result window is too large` is being hit, check
  `index.max_result_window` via `GET /<index>/_settings` to see if it was
  already raised from the 10,000 default as a prior workaround.
- Use the slow log (`index.search.slowlog`) or profile a specific deep
  page request with `"profile": true` to confirm per-shard sort/collect
  time growing with `from` depth, distinguishing this from an unrelated
  slow-query cause.
- Identify the actual use case behind the deep pagination: a human
  clicking through UI pages (rare past the first few pages in practice),
  versus an export/sync job walking the full dataset (the common real
  cause of very deep `from` values).

## Fix
- For sequential "next page" access patterns (UI infinite scroll, forward-
  only pagination), replace `from`+`size` with `search_after`, sorting on
  a field with unique, stable ordering (typically the sort field plus
  `_id` or `_shard_doc` as a tiebreaker) -- each request carries the last
  seen sort values instead of an offset, so per-request cost stays
  constant regardless of depth.
- For full-index export/walk jobs, use a Point-in-Time (`POST
  /<index>/_pit`) combined with `search_after`, which gives a consistent
  snapshot across the whole walk (avoiding skipped/duplicated documents
  from concurrent writes) and doesn't have the 10,000-depth ceiling.
- For a one-off full scan rather than a live paginated UI, the `scroll`
  API remains valid, though PIT+`search_after` is the currently preferred
  approach for most cases since it doesn't hold a scroll context open
  server-side for the whole walk.
- Only raise `index.max_result_window` as a genuinely temporary
  stopgap while migrating callers to `search_after`/PIT, not as the
  final fix -- it removes the safety rail but not the underlying cost.

## Pitfalls
- `search_after` requires a deterministic sort order with a tiebreaker;
  omitting a unique tiebreaker field (relying on a non-unique sort field
  alone) can produce skipped or duplicated results across pages when
  multiple documents share the same sort value.
- Leaving PIT contexts open without a `keep_alive` renewal strategy (or
  forgetting to close them via `DELETE /_pit` when a walk finishes early)
  leaks resources on data nodes over time, similar to leaked scroll
  contexts.
- Allowing a UI to still expose "jump to page N" for arbitrary N is
  incompatible with `search_after`'s sequential-access model -- if random
  page access is a genuine product requirement, that's a sign the UI
  design itself needs to change (e.g. to cursor-based "next/previous"),
  not just the backend query.

## Verify
Re-run the previously slow deep-page request pattern using `search_after`
(or PIT+`search_after`) and confirm response latency stays roughly flat
across page depth rather than increasing, and confirm
`index.max_result_window` can be left at or restored to its default once
no caller still issues deep `from` requests (check access logs for
lingering `from` values above a few hundred).
