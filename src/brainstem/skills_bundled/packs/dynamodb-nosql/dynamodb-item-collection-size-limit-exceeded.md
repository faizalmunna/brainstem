---
name: dynamodb-item-collection-size-limit-exceeded
description: Writes to a DynamoDB single-table design fail with an item collection size limit error because one partition key's items plus its indexed attributes exceeded 10GB.
triggers: ["dynamodb item collection size limit exceeded", "dynamodb 10gb partition limit", "ItemCollectionSizeLimitExceededException", "dynamodb local secondary index 10gb", "single table design partition growing too large"]
permissions: ["READ"]
---

## Symptom
Writes (specifically `PutItem`, `UpdateItem`, or `BatchWriteItem`) to
items under a particular partition key start failing with
`ItemCollectionSizeLimitExceededException`, even though the table overall
is nowhere near any documented per-table size limit -- because DynamoDB
has no such per-table size cap. The failure is scoped to one partition
key's **item collection** (all items sharing that partition key, across
the base table and any Local Secondary Indexes) exceeding 10GB, a hard
limit that exists specifically because LSIs are co-located with base data
on the same physical partition.

## Likely causes
1. **A single-table design intentionally packs many related entity types
   under one partition key** (e.g. everything for `CUSTOMER#123`: profile,
   orders, line items, events) as a deliberate denormalization strategy,
   and for a sufficiently large or long-lived tenant/customer, that
   collection's cumulative size crosses 10GB before anyone re-evaluates
   the access pattern.
2. **One or more Local Secondary Indexes exist on the table**, and LSIs
   count toward the same 10GB item-collection limit as the base items
   (unlike GSIs, which are stored and limited independently) -- a table
   design that seemed fine on raw item size alone can hit the ceiling
   sooner than expected once LSI-projected attribute copies are counted.
3. **An unbounded, ever-growing child collection is modeled as items under
   a single fixed parent partition key** -- e.g. an audit log, event
   history, or time-series data stored as `PARENT#123` / `EVENT#<timestamp>`
   sort keys with no time-based or count-based partitioning, so the
   collection grows without bound for long-lived parents.
4. **Large attribute values (embedded blobs, big JSON documents, long
   text fields) are stored directly as item attributes** rather than
   externalized to S3 with a reference stored in DynamoDB, inflating
   average item size and therefore how quickly a given item count reaches
   the 10GB ceiling.

## Diagnose
- The error itself (`ItemCollectionSizeLimitExceededException`) only
  occurs on tables that have at least one LSI -- confirm the table's index
  configuration; if there are no LSIs, this specific error can't occur and
  the symptom is a different write failure.
- Use `DescribeTable` and, if item-collection metrics are enabled, check
  `ItemCollectionMetrics` returned on write responses (available when
  `ReturnItemCollectionMetrics` is set on `PutItem`/`UpdateItem`/
  `BatchWriteItem`) to see the current size of the affected item
  collection directly.
- Query the suspected hot partition key and sum item sizes (or use the
  approximate size estimate from a full `Query` with pagination) to
  confirm it's approaching or has crossed 10GB.
- Review the table's access-pattern design (or single-table design ER
  diagram, if one exists) for which entity types share a partition key
  with the growing collection, and identify which one is actually
  unbounded (grows with time or event count) versus fixed-size (grows
  with a bounded set of attributes).

## Fix
For unbounded child collections (logs, events, time-series data under a
parent), introduce **time-based or count-based partitioning**: instead of
one partition key per parent forever, roll the partition key over per
period (`PARENT#123#2026-09`) or shard by a bounded counter, so no single
collection grows indefinitely. This also generally improves query
performance since most access patterns want "the last N" or "this month's"
data, not the entire lifetime history in one query. For large embedded
attributes, externalize them: store the blob/document in S3 and keep only
a reference (bucket/key, or a presigned URL generated on read) in the
DynamoDB item, which is standard practice for anything approaching the
400KB single-item limit anyway and directly reduces collection size
growth per item. If LSIs are the actual constraint (base data alone isn't
large but LSI-projected copies push the collection over 10GB), evaluate
whether the access patterns the LSI serves can instead be served by a GSI
-- GSIs are stored separately and aren't subject to the same 10GB
co-located limit, at the cost of eventual (not strong) consistency on
reads from that index.

## Pitfalls
Migrating an LSI to a GSI is not a drop-in swap -- GSIs require their own
provisioned/on-demand capacity, only support eventually consistent reads
(LSIs can be read strongly consistent), and existing queries relying on
strong consistency against the LSI need to be re-evaluated for whether
eventual consistency is acceptable. Also, simply switching to time-based
partition key rollover without updating read-path code to fan out across
the relevant period buckets silently makes older data unreachable by the
existing query pattern -- the migration has to update both write and read
paths together, and existing large collections need a backfill/re-key
strategy, not just a change going forward.

## Verify
After re-partitioning, confirm new writes under the affected logical
entity are landing under multiple partition keys (period- or
shard-suffixed) rather than one, and that no `ItemCollectionSizeLimitExceededException`
occurs during a write burst sized to match or exceed the volume that
originally triggered the error. If item-collection metrics were enabled,
confirm the per-collection size for each new shard/period key stays well
under 10GB under expected retention before the next rollover.
