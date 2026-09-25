---
name: dynamodb-hot-partition-key-throttling
description: A DynamoDB table throttles requests for one popular partition key (a big tenant, a common status value) while the table's aggregate consumed capacity looks fine.
triggers: ["dynamodb ProvisionedThroughputExceededException on one customer", "dynamodb throttling but capacity graph looks fine", "dynamodb hot key one tenant", "dynamodb partition key skew", "why is only one customer getting throttled in dynamodb"]
permissions: ["READ"]
---

## Symptom
A subset of requests -- often traced back to one specific tenant ID,
device ID, or a low-cardinality attribute like `status` used directly as
the partition key -- return `ProvisionedThroughputExceededException` (or,
in on-demand mode, elevated latency and throttling on that key range),
while the table-level `ConsumedReadCapacityUnits`/`ConsumedWriteCapacityUnits`
CloudWatch metrics stay well under the provisioned or account-default
ceiling. The team's first instinct is to raise table-level throughput,
which doesn't fix it, because the problem isn't aggregate capacity -- it's
that DynamoDB divides provisioned (or adaptive) capacity across physical
partitions by key, and one partition is being hit far harder than others.

## Likely causes
1. **A single partition key value dominates traffic** -- a large tenant in
   a multi-tenant table keyed by `tenantId`, a celebrity user, or a viral
   item -- so a disproportionate share of requests lands on the one
   physical partition holding that key's item collection, and each
   partition has its own hard throughput ceiling (historically ~3,000 RCU
   / ~1,000 WCU per partition) regardless of what's provisioned table-wide.
2. **A low-cardinality attribute is used as the whole partition key**, most
   commonly a `status` field (`PENDING`, `ACTIVE`, `COMPLETE`) or a date
   bucket (`2026-09-20`) -- every item sharing that status/date collapses
   onto the same partition, so write-heavy state transitions or a single
   "today" bucket become a chokepoint no matter how the table's total
   capacity is sized.
3. **Adaptive capacity hasn't kicked in yet or can't keep up** -- adaptive
   capacity isolates and boosts hot partitions automatically, but it reacts
   over a window of sustained imbalance, not instantaneously, so a sudden
   spike in traffic to one key can throttle for the seconds-to-low-minutes
   it takes adaptive capacity to redistribute, especially right after the
   spike begins.
4. **Bursting on a single key exhausts the per-partition burst credit
   pool** faster than table-level metrics reveal, because burst capacity
   is also tracked per-partition, not just table-wide, so a key that was
   idle and then spikes can throttle even though it "should" have burst
   headroom by the table's aggregate numbers.

## Diagnose
- Enable **Contributor Insights for DynamoDB** on the table (and any
  affected GSI) and look at the "most accessed keys" report -- it directly
  names the specific partition key values generating the most read/write
  traffic and throttled requests, which is the fastest way to confirm a
  hot key versus a diffuse problem.
- Compare per-key request volume against the table's total: if one
  `tenantId` or `status` value accounts for a share of requests wildly out
  of proportion to its share of total items, that's the hot partition.
- Check CloudWatch for `ThrottledRequests` alongside `ConsumedReadCapacityUnits`
  / `ConsumedWriteCapacityUnits` at the table level -- throttling with
  headroom in the aggregate metric is the signature of a per-partition
  limit being hit, not a table-wide capacity shortage.
- Review the table's key schema and application code for what value
  populates the partition key -- specifically check for enum-like fields
  (`status`, `type`, `region`) or any field with materially fewer distinct
  values than the item count.

## Fix
Redesign the partition key so traffic spreads across many physical
partitions instead of collapsing onto few. The standard pattern is **write
sharding**: append a calculated suffix (a random number in a fixed range,
or a hash of a high-cardinality attribute like item ID) to the hot key,
e.g. `STATUS#PENDING#7` instead of `STATUS#PENDING`, distributing writes
for that logical group across N physical partitions. Reads then need to
fan out across all N shards and merge results (acceptable for aggregate
queries, since you're trading one cheap query for N cheap parallel
queries instead of one throttled one). For the multi-tenant "one big
tenant" case, add a secondary dimension to the key -- compose the
partition key from `tenantId` plus a natural high-cardinality sub-entity
(e.g. `tenantId#userId`) so a single large tenant's items are spread
across many partitions rather than sharing one. Choose the shard count
based on expected peak throughput divided by the per-partition ceiling,
with margin.

## Pitfalls
Sharding a key that didn't need it adds real complexity (fan-out reads,
merge logic, harder pagination) for no benefit -- confirm via Contributor
Insights that a specific key is actually hot before sharding, rather than
sharding defensively. Also, a common half-fix is switching the table to
on-demand capacity mode expecting it to eliminate hot-partition throttling
-- on-demand still allocates capacity per-partition internally and can
still throttle a sufficiently skewed single key during a sudden spike,
because scaling responds to sustained load patterns, not instant
step-changes on one key.

## Verify
After sharding, re-run the Contributor Insights "most accessed keys"
report and confirm request volume for the formerly-hot logical key is now
distributed across its N shard suffixes roughly evenly, and confirm
`ThrottledRequests` for the table (and any read path querying the sharded
key) stays at zero under a load test that reproduces the original traffic
pattern targeted at the previously-hot key.
