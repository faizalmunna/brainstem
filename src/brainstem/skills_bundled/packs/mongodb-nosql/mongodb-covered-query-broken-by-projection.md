---
name: mongodb-covered-query-broken-by-projection
description: Diagnose a MongoDB query that stops being served entirely from the index and starts fetching full documents after a seemingly unrelated projection or schema change.
triggers: ["query was fast now its slow after adding a field", "covered query stopped being covered", "index only query now fetching documents", "explain shows FETCH stage appeared", "query regression after adding a projected field"]
permissions: ["READ"]
---

## Symptom
A previously fast, high-throughput query (often a hot-path lookup used
very frequently, like a permission check or a list endpoint) regresses
in latency after what looks like an unrelated change -- adding a field
to the projection, adding a field to the schema that a middleware/ORM
layer now includes by default, or a driver upgrade that changes default
field inclusion -- even though no index was dropped and the filter
predicate didn't change.

## Likely causes
1. **The query was a "covered query"** (able to be answered entirely
   from the index, without fetching the actual documents) **and a
   projection or schema change added a field not present in the
   index**, forcing MongoDB to add a `FETCH` stage to retrieve full
   documents -- the query still uses the index to find matching
   documents, but now also pays the cost of fetching each one from the
   collection, which is a meaningfully different (and much larger) cost
   profile at high query volume.
2. **An ORM/ODM or middleware layer changed its default field selection**
   (e.g. began including a new audit field, or switched from explicit
   projection to `SELECT *`-equivalent behavior) without anyone
   realizing this silently broke index coverage for a hot query, since
   nothing about the application's explicit query code changed.
3. **The index was created to match an old, narrower projection**, and
   as the document schema evolved (new fields added to documents over
   time), nobody revisited whether the covering index should be
   extended to keep covering the query's current field list.
4. **`_id` inclusion assumptions** -- a projection that excludes `_id`
   needs to explicitly do so (`{_id: 0}`); if code relied on an index
   covering a query but the index doesn't include `_id` and the
   projection doesn't exclude it, `_id` alone can force a fetch even
   when every other projected field is covered.

## Diagnose
- Run `.explain("executionStats")` on the query before and after the
  change (or against a recent known-good baseline if available) and
  check for the presence of a `FETCH` stage -- a covered query's plan
  shows only an `IXSCAN` (and `PROJECTION_COVERED` in newer versions);
  a regressed one shows `IXSCAN` followed by `FETCH`.
- Compare the exact field list returned by the query (including any
  fields an ORM/middleware silently adds) against the index's field
  list -- any field in the result that isn't part of the index (and
  isn't `_id`, if `_id` is included) breaks coverage.
- Check `totalDocsExamined` in the explain output -- for a genuinely
  covered query this should be 0 (or absent); a nonzero value confirms
  documents are being fetched, not just index-scanned.
- Correlate the regression's start time against recent deploys (schema
  changes, ORM/library version bumps, projection changes in code) using
  deploy history, to identify which specific change broke coverage.

## Fix
- Extend the index to include every field the query actually projects
  (turning it back into a covering index for the current query shape),
  if the query is hot enough that the extra index size is worth the
  read-latency win -- weigh this against write overhead like any other
  indexing decision.
- Alternatively, tighten the query's projection back to only the fields
  actually needed by the caller, if the newly included field(s) were
  added incidentally (an ORM default, an over-broad `SELECT *`-style
  fetch) rather than a genuine new requirement -- this is often the
  better fix since it also reduces network payload, not just index
  coverage.
- If using an ORM/ODM, configure explicit field selection for hot-path
  queries rather than relying on framework defaults that can silently
  change between versions -- make the projection a deliberate,
  reviewed part of the query rather than an implicit side effect of
  the object mapping layer.
- Re-review covering indexes periodically as schema evolves (part of
  the same audit as `$indexStats` review in
  `mongodb-compound-index-field-order`) so coverage doesn't silently
  erode as new fields get added to documents and queries over time.

## Pitfalls
- Extending an index to restore coverage without checking whether the
  newly included field has high cardinality/large values -- a covering
  index that includes a large text field bloats index size
  substantially and can itself contribute to working-set memory
  pressure (see `mongodb-working-set-thrashing-under-read-load`);
  covering isn't free.
- Assuming any query using an index at all is "fast" -- an `IXSCAN` with
  a subsequent `FETCH` is still much better than a collection scan, but
  a regression from fully-covered to fetch-per-document can still be a
  meaningful latency/throughput hit at high query volume, so don't
  dismiss it just because an index is technically involved.
- Fixing this for one query without checking whether the same
  ORM/middleware default change broke coverage for other hot-path
  queries using the same model/collection -- a default field-inclusion
  change tends to affect every query through that code path, not just
  the one that happened to get noticed first.

## Verify
Re-run `.explain("executionStats")` on the query and confirm
`totalDocsExamined` is 0 with no `FETCH` stage in the winning plan (or
confirm `PROJECTION_COVERED` on versions that report it explicitly),
then measure query throughput/latency under production-representative
load and confirm it's back to the pre-regression baseline.
