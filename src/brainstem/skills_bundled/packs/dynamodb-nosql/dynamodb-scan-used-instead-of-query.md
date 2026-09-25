---
name: dynamodb-scan-used-instead-of-query
description: A DynamoDB read operation consumes far more capacity than expected and times out on large tables because Scan is used where Query on a known key should have been.
triggers: ["dynamodb scan consuming too much capacity", "dynamodb scan timing out", "dynamodb read costs way higher than expected", "dynamodb full table scan slow", "should I use scan or query in dynamodb"]
permissions: ["READ"]
---

## Symptom
A read operation against a DynamoDB table is slow (multi-second or
timing out), consumes read capacity wildly disproportionate to the number
of items actually needed by the caller, and CloudWatch's
`ConsumedReadCapacityUnits` shows large spikes correlated with that
specific operation. Cost also climbs faster than item count or traffic
growth would explain. The operation in question turns out to be a `Scan`
(with a `FilterExpression` to narrow results) where the access pattern
actually has a known key or key prefix that a `Query` could have used
directly.

## Likely causes
1. **`Scan` with a `FilterExpression` is used to find items matching an
   attribute that isn't the partition key**, because it's the most
   SQL-`WHERE`-intuitive way to write the request -- but DynamoDB applies
   the filter *after* reading and charging for every item in the segment
   scanned, not before, so capacity consumption is proportional to total
   table size, not to the number of matching results.
2. **No GSI exists for the actual access pattern**, so even though the
   team knows they always look up items by, say, `customerEmail`, there's
   no index with `customerEmail` as a key -- `Scan`-and-filter became the
   path of least resistance instead of adding the index the access
   pattern actually needs.
3. **The table's primary key design doesn't match the dominant query
   pattern** -- e.g. partition key is `itemId` but the application almost
   always needs "all items for this order," which requires a `Query` on
   an `orderId`-keyed index or a composite key, and in the absence of
   that, a full `Scan` with a filter substitutes for the missing access
   path.
4. **A `Scan` was reasonable at prototype scale (few hundred items) and
   was never revisited as the table grew** -- correct-looking code at low
   item counts becomes a capacity and latency problem specifically because
   `Scan` cost scales with table size, not query selectivity, so the
   regression is invisible until the table crosses a size threshold.

## Diagnose
- Search application code for `Scan` calls (or ORM/SDK equivalents like
  `.scan()`) and check whether each one includes a `FilterExpression` --
  that combination is the direct signature of "should probably be a
  Query."
- Check CloudWatch for the operation-level metric
  `ConsumedReadCapacityUnits` with the `Operation` dimension set to
  `Scan` versus `Query`, and compare consumed capacity to item counts
  actually returned to the caller (available in the response's `Count`
  vs `ScannedCount` -- a `ScannedCount` far higher than `Count` confirms
  the filter is discarding most of what was read and paid for).
- Review the table's and any GSIs' key schemas against the attribute used
  in the `FilterExpression` -- if that attribute isn't a partition or
  sort key anywhere, there's no way to `Query` it as-is, confirming an
  index gap rather than just a code-level mistake.
- For time-boxed investigation, run the suspect `Scan` against a
  non-production table copy with `ReturnConsumedCapacity: TOTAL` set, and
  compare the reported capacity units against what an equivalent `Query`
  (once an appropriate index exists) would consume for the same logical
  result set.

## Fix
Replace the `Scan`+filter with a `Query` against a key that matches the
access pattern -- if no such key exists yet, add a GSI with the filtered
attribute (or a composite of it) as the partition key, then query that
index directly. This changes cost and latency from O(table size) to
O(matching items), which is the entire point of DynamoDB's key-based
access model. Where the access pattern is inherently "look at everything"
(a genuine full-table export, an analytics job, a one-off migration),
`Scan` is the correct tool, but should run with reduced-priority handling
-- lower `Limit` per page with pagination and deliberate pacing (or a
parallel scan with a bounded number of segments), on-demand or headroom
capacity, and ideally routed through DynamoDB's export-to-S3 or a stream-
based pipeline rather than a live application-path `Scan`, so it doesn't
compete with real-time traffic for the same provisioned capacity.

## Pitfalls
Adding a GSI to fix this replaces a `Scan` problem with a new "GSI has its
own capacity and key-skew characteristics" problem (see the GSI-specific
skill in this pack) -- don't assume adding any index is free of the same
hot-key risk the base table has. Also, a common half-fix is keeping the
`Scan` but adding `Limit` and pagination to "reduce" capacity per call --
this reduces capacity *per request* but doesn't reduce the *total*
capacity consumed to read through the whole table across all the
paginated calls, so it fixes timeout risk without fixing underlying cost.

## Verify
Re-run the access pattern as a `Query` against the new/existing key and
compare `ConsumedReadCapacityUnits` and `Count`/`ScannedCount` in the
response against the original `Scan` for the same logical result --
confirm `ScannedCount` now equals or closely tracks `Count` (little to no
wasted read), and confirm p99 latency for the operation drops to a level
consistent with a bounded key lookup rather than scaling with table size.
