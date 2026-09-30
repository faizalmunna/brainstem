---
name: mongodb-aggregation-pipeline-match-too-late
description: Diagnose a MongoDB aggregation pipeline that processes far more documents than necessary because filtering happens after expensive stages instead of before them.
triggers: ["aggregation pipeline slow", "aggregate query taking forever", "pipeline processing too many documents", "aggregation using too much memory", "why is my $group so slow"]
permissions: ["READ"]
---

## Symptom
An aggregation pipeline is slow or memory-intensive (sometimes hitting
the 100MB per-stage memory limit and requiring `allowDiskUse`) even
though the final result set is small -- the pipeline is doing real work
on far more documents than end up mattering, because the stage that
actually narrows the working set (`$match`) comes late in the pipeline,
after `$lookup`, `$unwind`, `$group`, or `$sort` have already processed
the full, unfiltered input.

## Likely causes
1. **`$match` placed after `$lookup` or `$unwind`** -- the pipeline joins
   or expands every document first and only filters afterward, so the
   expensive join/expansion work is done against the entire collection
   instead of the subset that will actually survive the filter.
2. **`$match` placed after `$group`** -- the pipeline aggregates over
   every document in the collection, then filters the (potentially much
   smaller) grouped results, when the underlying documents could have
   been filtered before grouping to reduce how much data feeds the
   `$group` stage.
3. **Pipeline built incrementally over time** -- stages were added in
   the order features were requested (e.g. a filter added last because
   it was the most recently requested feature) rather than reordered
   for efficiency, and nobody revisited stage order as the pipeline
   grew.
4. **A filter condition that could be pushed earlier depends on a field
   computed by an earlier stage** (a legitimate case), which is
   different from a filter that *could* run first but simply wasn't
   placed there -- distinguishing these matters because only the latter
   is a straightforward reordering fix.
5. **No index supports the early `$match`**, so even after reordering,
   the first stage still does a collection scan -- reordering helps
   correctness of pipeline efficiency but doesn't replace needing an
   index for the initial filter.

## Diagnose
- Run `.explain("executionStats")` on the aggregation and check whether
  the plan shows an index being used for the first `$match` stage
  (look for `IXSCAN` at the start of the explain output) versus a
  `COLLSCAN` processing the full collection before any filtering.
- Check the number of documents entering each stage vs. leaving it
  (`explain` in newer MongoDB versions reports per-stage document
  counts, or add a `$count` stage temporarily after each candidate
  reorder point) to find exactly which stage is processing an
  unnecessarily large input.
- Review the pipeline for any `$match` (or `$limit`) stage that appears
  after a `$lookup`, `$unwind`, or `$group` and check whether its filter
  condition only references fields available *before* those stages --
  if so, it's a candidate to move earlier.
- Check whether `allowDiskUse: true` is set or was required to make the
  pipeline succeed at all -- needing it is itself a signal that a stage
  is processing more data than fits comfortably in memory, often fixable
  by narrowing input earlier rather than just tolerating disk spill.

## Fix
- Move every `$match` condition that doesn't depend on a later
  computed/joined field as early as possible in the pipeline -- ideally
  first, so MongoDB can use an index to satisfy it and avoid a full
  collection scan before any other processing happens.
- Where a filter genuinely depends on a `$lookup` result, apply a
  partial pre-filter before the `$lookup` on whatever fields are
  available pre-join (narrowing the join's input), and keep only the
  join-dependent portion of the filter after it -- don't defer the
  entire filter just because part of it needs to.
- For `$lookup` specifically, use the pipeline-style `$lookup` (with a
  `let`/pipeline sub-query, including its own `$match`) instead of the
  simple `localField`/`foreignField` form when the foreign collection is
  large, so filtering happens inside the join itself rather than
  materializing every match and filtering afterward.
- Add `$limit` early when only a bounded number of results are ultimately
  needed (e.g. paginated results) and the pipeline's ordering allows it,
  so downstream stages process a bounded input instead of the full
  matching set.
- Ensure the field(s) used in the earliest `$match` are indexed --
  reordering the pipeline only pays off fully if the first stage can
  use an index rather than scanning.

## Pitfalls
- Reordering `$match` before `$unwind` changes semantics if the filter
  references a field *inside* the array being unwound -- a filter on
  `arr.field` needs to stay after (or be expressed carefully around) the
  `$unwind` that produces per-element documents, or it silently filters
  on the wrong thing (the first array element, or nothing).
- Moving `$match` earlier without checking that a supporting index
  exists just moves the same collection scan earlier in the pipeline --
  it can still help (less work downstream) but doesn't fully solve the
  performance problem; pair pipeline reordering with proper indexing.
- Splitting one `$match` across two places (part before `$lookup`, part
  after) needs enough care that the combined result is still correct --
  double-check with a known test case that the split filter doesn't
  accidentally become an OR instead of an AND of the original
  conditions.

## Verify
Re-run `.explain("executionStats")` on the reordered pipeline and
confirm the document count entering the first heavy stage (`$lookup`,
`$group`, `$unwind`) is close to the final result count rather than the
full collection size, and confirm the pipeline no longer requires
`allowDiskUse` (or uses substantially less memory) under representative
production data volume.
