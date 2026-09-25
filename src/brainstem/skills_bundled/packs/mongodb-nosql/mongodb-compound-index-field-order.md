---
name: mongodb-compound-index-field-order
description: Diagnose a compound MongoDB index that exists but still isn't used efficiently because its field order doesn't match the actual query pattern.
triggers: ["index exists but query still slow", "compound index not being used efficiently", "explain shows index scan but still slow", "why isnt mongodb using my index", "index scan examining too many documents"]
permissions: ["READ"]
---

## Symptom
A query filters or sorts on fields that are covered by an existing
compound index, `.explain()` even shows the index being used (`IXSCAN`),
and yet the query is still slow and examines far more documents/index
keys than it returns -- the natural assumption ("I have an index on
these fields, so it should be fast") turns out to be wrong because
*having* an index and having an index *usable for this exact query
shape* are different things.

## Likely causes
1. **Field order in the compound index doesn't match the query's
   equality/sort/range (ESR) usage.** A compound index on `(a, b, c)`
   efficiently supports equality filters on `a`, then `b`, then range/sort
   on `c` in that order -- but a query that filters on `b` and `c` without
   `a`, or that sorts on a field that isn't the index's trailing usable
   field given the other predicates, can't use the index as efficiently
   as its existence suggests.
2. **The index supports the filter but not the sort**, forcing MongoDB to
   fetch matching documents via the index and then perform an in-memory
   sort (`SORT` stage, potentially hitting the 100MB sort memory limit
   and spilling to disk) instead of returning results in index order.
3. **A range condition on a field placed before other equality fields
   in the index** breaks the ability to use subsequent index fields
   efficiently -- e.g. an index on `(createdAt, status)` with a query
   that ranges on `createdAt` and equality-filters on `status` can't use
   the index to narrow by `status` the way `(status, createdAt)` would.
4. **Multiple similar-looking indexes exist and the planner chooses a
   different one than expected**, or an old index from an earlier query
   pattern is still present and technically "matches" well enough to be
   selected while being far from optimal for the current dominant query.

## Diagnose
- Run `.explain("executionStats")` on the actual production query
  (with realistic parameter values, not a trivial example) and check
  `totalKeysExamined` and `totalDocsExamined` against `nReturned` -- a
  large gap means the index is being used, but inefficiently.
- Check whether the winning plan includes a `SORT` stage after the
  `IXSCAN` -- this confirms the index satisfies the filter but not the
  sort, meaning an in-memory sort is happening on every query execution.
- Apply the ESR (Equality, Sort, Range) rule to the query by hand:
  list the fields used for equality matches, then the sort field, then
  range/inequality fields, and compare that order against the actual
  index's field order -- a mismatch here is the direct, checkable root
  cause, not a guess.
- Use `.explain()`'s `rejectedPlans` (in verbose mode) or `hint()` to
  force the index you expect and compare its stats against whatever the
  planner chose by default -- if the hinted plan is meaningfully
  better, the planner is choosing correctly given the index it has, and
  the fix is the index shape itself, not the planner's choice.

## Fix
- Rebuild the compound index in ESR order matching the actual dominant
  query: equality-filtered fields first, then the field used for
  sorting, then range-filtered fields last -- e.g. a query doing
  `find({status: "pending"}).sort({createdAt: 1})` wants
  `{status: 1, createdAt: 1}`, not `{createdAt: 1, status: 1}`.
  For a query design shape reference, see `mongodb-unindexed-query-backing-up-job-queue`
  which shows this pattern applied to a queue-polling query specifically.
- Where multiple query shapes against the same collection are equally
  important and can't share one field order, create separate compound
  indexes tailored to each shape rather than trying to force one index
  to serve every pattern -- balance this against write overhead (each
  additional index costs on every insert/update).
- Remove indexes that no longer match any active query pattern (check
  via `db.collection.aggregate([{$indexStats:{}}])` for per-index usage
  counts) -- an unused or superseded index still consumes memory in the
  working set and write overhead without benefiting any query.
- If the query has both a range filter and needs a different sort, and
  the two can't coexist efficiently in a single compound index, consider
  whether the query can be restructured (e.g. paginate by an indexed
  field instead of an arbitrary sort) rather than fighting the
  index/query shape mismatch.

## Pitfalls
- Adding more fields to the compound index "to be safe" without
  respecting ESR order gives a false sense of coverage -- an index with
  the right fields in the wrong order can perform barely better than no
  index at all for the query that matters.
- Creating a new, better-ordered index without dropping the old one that
  no longer serves any query adds write overhead and working-set memory
  pressure for zero read benefit -- audit with `$indexStats` before and
  after, don't just add.
- Over-indexing for every conceivable query shape defeats the purpose --
  each additional index slows every write to the collection and
  competes for cache space (see `mongodb-working-set-thrashing-under-read-load`);
  index for actual, measured query patterns.

## Verify
Re-run `.explain("executionStats")` on the production query pattern
against the rebuilt index and confirm `totalKeysExamined` is close to
`nReturned`, with no `SORT` stage in the winning plan, then check
`$indexStats` after a representative production traffic window to
confirm the new index is actually the one being selected and used at
the expected volume.
