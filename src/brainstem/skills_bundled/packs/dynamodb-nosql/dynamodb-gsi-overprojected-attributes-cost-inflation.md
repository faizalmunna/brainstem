---
name: dynamodb-gsi-overprojected-attributes-cost-inflation
description: A DynamoDB table's storage cost and write capacity usage are unexpectedly high because a GSI projects ALL attributes instead of only the ones its queries need.
triggers: ["dynamodb gsi storage cost higher than expected", "dynamodb ProjectionType ALL vs KEYS_ONLY vs INCLUDE", "dynamodb every write more expensive after adding index", "dynamodb gsi doubling table storage", "why is my dynamodb bill so high after adding an index"]
permissions: ["READ"]
---

## Symptom
After adding one or more GSIs to support new query patterns, the table's
storage cost and/or write capacity consumption increases by far more than
the query benefit seems to justify -- sometimes roughly doubling or more
per additional GSI. Every base-table write now costs more WCU than
before, even for writes to attributes the GSI's queries never actually
read. The GSI was defined with `ProjectionType: ALL` (copying every
attribute from the base item into the index) as the default, easy choice,
without checking whether the queries run against that index actually need
more than the key attributes plus a handful of others.

## Likely causes
1. **The GSI projection type is `ALL` by default/habit**, copying every
   attribute of every indexed item into the GSI's own storage -- which
   means the table is effectively storing (and paying to write) a near-
   complete duplicate of the base table's data for each such GSI, not
   just the index structure itself.
2. **The queries actually run against the GSI only need a handful of
   attributes** (commonly just the key attributes for a lookup that then
   fetches the full item from the base table anyway, or a small display
   projection for a list view), so most of what `ALL` projects is never
   read through that index at all -- pure storage and write-cost overhead
   with no corresponding read benefit.
3. **Every base-table write that touches a projected attribute also
   writes to the GSI's copy of it**, so a large item with many attributes,
   fully projected into a GSI via `ALL`, means routine updates to
   unrelated fields on that item still incur GSI write cost proportional
   to the full projected item size, not just the fields that actually
   changed.
4. **Multiple GSIs on the same table each independently use `ALL`
   projection**, compounding the effect -- a table with three GSIs all
   projecting all attributes can be storing (and paying write costs for)
   roughly four full copies of every item's data (base plus three index
   copies) for query patterns that in most cases only need key attributes
   plus a small projection.

## Diagnose
- Run `DescribeTable` and check each GSI's `Projection.ProjectionType`
  and, if `INCLUDE`, its `NonKeyAttributes` list -- flag any GSI set to
  `ALL` as a candidate for review.
- For each `ALL`-projected GSI, review the actual query code that reads
  from it and list which attributes are read from the query result versus
  which are ignored (or whether the code only reads the key and then
  issues a separate `GetItem` against the base table for the rest) --
  attributes never read from GSI query results are pure overhead.
- Compare table storage size against expected size from item count times
  average base-item size -- storage significantly higher than that
  back-of-envelope number, scaled by number of `ALL`-projected GSIs, is a
  strong confirming signal.
- Check `ConsumedWriteCapacityUnits` broken out by whether writes touch
  large items with many attributes versus small ones, and correlate with
  GSI projection settings -- writes to large, fully-projected items should
  show visibly higher WCU consumption than a base-table-only estimate
  would predict.

## Fix
Change each GSI's projection to the minimum that its actual query
patterns need: `KEYS_ONLY` when queries only need to identify matching
items (and the caller does a follow-up `GetItem` against the base table
for the rest, which is often cheap and simple enough to be worth it), or
`INCLUDE` with an explicit, small `NonKeyAttributes` list for query
patterns that need a few specific display/filter attributes but not the
whole item. This is a projection-type change, which (unlike most GSI key
changes) requires creating a replacement GSI with the new projection
settings and migrating query code to it, then deleting the old one --
GSI projection type can't be changed in place on an existing index. Audit
this per-GSI, per-table, since different indexes on the same table may
legitimately need different projection levels depending on what their
specific queries read.

## Pitfalls
Switching to `KEYS_ONLY` for a query pattern that actually does need
several attributes just moves the cost from GSI write amplification to
extra `GetItem` read calls and added latency per query (fetch from index,
then fetch again from base table) -- for high-QPS read paths this
round-trip cost can outweigh the storage/write savings, so `INCLUDE` with
a deliberately chosen small attribute set is often the better middle
ground rather than defaulting to the opposite extreme. Also, remember
that reducing a GSI's projection doesn't retroactively shrink already-
written storage cost accounting mid-cycle the way changing on-demand
settings might feel like it should -- it only affects new/updated items
going forward through the new GSI, so a full projection-type migration
(new index, backfill, cutover, delete old index) is required to fully
capture the savings.

## Verify
After migrating affected GSIs to `KEYS_ONLY`/`INCLUDE`, compare table
storage size and `ConsumedWriteCapacityUnits` for a representative period
against the pre-change baseline for the same traffic pattern, and confirm
the reduction roughly matches the expected drop from no longer
duplicating unused attributes per index. Confirm query code reading from
the migrated GSI still returns correct results (either directly from the
narrower projection or via the added `GetItem` fallback), with no
missing-attribute errors in application logs.
