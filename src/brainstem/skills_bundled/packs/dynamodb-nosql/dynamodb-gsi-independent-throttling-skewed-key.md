---
name: dynamodb-gsi-independent-throttling-skewed-key
description: Writes to a DynamoDB table throttle or fail because a Global Secondary Index has a more skewed key distribution than the base table, even though the base table itself is healthy.
triggers: ["dynamodb gsi throttling but base table fine", "dynamodb WriteThrottleEvents on index", "gsi ProvisionedThroughputExceededException base table healthy", "dynamodb global secondary index capacity separate from table", "why does my gsi throttle when the main table doesn't"]
permissions: ["READ"]
---

## Symptom
Base-table reads and writes succeed normally with healthy CloudWatch
metrics, but writes still fail or queue up with elevated latency, and
CloudWatch shows `ThrottledRequests`/`WriteThrottleEvents` scoped to a
specific **GSI**, not the base table. In provisioned mode this can even
throttle base-table writes entirely, because a write that would update a
throttled GSI is rejected at the base table too -- surprising teams who
expect GSI problems to stay contained to queries against that index.

## Likely causes
1. **The GSI's partition key has different (usually worse) cardinality
   than the base table's**, e.g. a table keyed by `orderId` (high
   cardinality, evenly distributed) has a GSI keyed by `customerId` or
   `status` for query convenience -- and that secondary key concentrates
   far more items per partition than the base key does, recreating the
   hot-partition problem independently on the index.
2. **GSI capacity is provisioned separately from the base table and was
   never sized to match actual write volume**, because every base-table
   write that touches an item with GSI key attributes generates a
   corresponding write to the GSI, so a GSI under-provisioned relative to
   the base table's write throughput throttles even when the base table
   has ample headroom.
3. **The GSI's key schema causes it to receive writes for nearly every
   base-table write**, e.g. a sparse-index pattern wasn't used and instead
   every item populates the GSI's key attributes, so the index absorbs the
   full write volume of the base table rather than a filtered subset --
   multiplying required GSI capacity beyond what was planned.
4. **In provisioned mode, a base-table write is rejected because its
   associated GSI write would exceed the index's provisioned capacity**,
   even though the base table itself has room -- DynamoDB enforces GSI
   capacity limits synchronously as part of the base write path, so a
   struggling GSI drags down base-table write availability too.

## Diagnose
- Check CloudWatch metrics scoped **per-GSI** (`ConsumedWriteCapacityUnits`,
  `ThrottledRequests` with the `GlobalSecondaryIndexName` dimension) --
  compare against the base table's own metrics for the same window to
  confirm the throttling is isolated to the index.
- Enable Contributor Insights for DynamoDB specifically on the GSI (it
  supports per-index reporting) and check the "most accessed keys" report
  for that index to see whether one GSI key value is disproportionately
  hot.
- Compare the GSI's provisioned RCU/WCU (or, on-demand, its independent
  scaling behavior) against the base table's -- GSIs have their own
  capacity settings in provisioned mode and commonly get overlooked during
  capacity planning since they're configured on a separate part of the
  console/IaC.
- Review the GSI's key schema against the base table's: count approximate
  distinct values for the GSI partition key attribute versus the base
  table's partition key attribute -- materially lower cardinality on the
  GSI side is the direct signal.
- Check whether every base-table item actually has the GSI's key
  attributes populated (a full index) versus only some items (a sparse
  index) -- a full index on a low-cardinality attribute is the worst-case
  combination.

## Fix
Treat the GSI's key design with the same scrutiny as the base table's --
it is a fully separate partitioning problem, not a free reflection of the
base table's distribution. If the natural query need is a low-cardinality
attribute (`status`, `category`), apply the same write-sharding pattern as
a hot base-table key: compose the GSI partition key from the low-cardinality
value plus a shard suffix or a naturally high-cardinality attribute, and
have query code fan out across shards. Where possible, make the index
**sparse** by only populating the GSI key attributes on items that
actually need to be queried that way, reducing the write volume the index
must absorb. Size GSI provisioned capacity independently based on its own
expected write volume (which for a full index equals the base table's
write volume, not a fraction of it), not copied from the base table's
numbers. In provisioned mode, treat "add a GSI" as "size a second table's
worth of write capacity," since that's functionally what's being added to
the write path.

## Pitfalls
A common half-fix is raising the GSI's provisioned WCU without addressing
key skew -- this raises the ceiling but doesn't fix an individual hot
partition within the index, since the added capacity still divides across
the same skewed key distribution. Another pitfall: switching just the GSI
to on-demand while leaving the base table on provisioned capacity is not
possible -- GSI capacity mode follows the base table's mode, so the fix
has to happen at the key-design level, not by mixing capacity modes per
index.

## Verify
Under a load test that reproduces production write patterns, confirm
per-GSI CloudWatch metrics (`ThrottledRequests` with the
`GlobalSecondaryIndexName` dimension) stay at zero, and confirm base-table
writes are no longer rejected due to GSI backpressure. If Contributor
Insights was used to identify a hot GSI key, re-check its "most accessed
keys" report post-fix to confirm the formerly hot value's traffic is now
distributed across shards or reduced via sparse indexing.
