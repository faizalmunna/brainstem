---
name: mongodb-hot-shard-from-poor-shard-key
description: Diagnose one MongoDB shard absorbing most read and write traffic while other shards sit nearly idle due to a poorly chosen shard key.
triggers: ["one shard maxed out others idle", "uneven load across mongodb shards", "sharded cluster hot shard", "shard key causing hotspot", "chunk migration not balancing load"]
permissions: ["READ"]
---

## Symptom
In a sharded MongoDB cluster, one shard consistently shows much higher
CPU, I/O, and operation counts than the others, which sit comfortably
under load -- despite the balancer reporting roughly even chunk counts
per shard. Adding more shards doesn't help throughput because new
capacity sits idle while the same one (or few) shard remains the
bottleneck for the dominant workload.

## Likely causes
1. **A monotonically increasing shard key** (e.g. an auto-incrementing
   ID, or an `ObjectId`/timestamp-prefixed key) means all *new* writes
   -- which are also disproportionately what gets *read* soon after
   being written in many workloads -- land on whichever single chunk
   currently owns the high end of the key range, concentrating both
   write and hot-read traffic on one shard regardless of how evenly
   chunks are balanced by count.
2. **A shard key with low cardinality** (e.g. sharding by `status` with
   only a handful of possible values, or by `country` when most traffic
   is from one region) means the natural data/traffic distribution is
   inherently uneven no matter how the balancer distributes chunks,
   because the key itself doesn't have enough distinct values to spread
   load evenly.
3. **Balanced chunk *count* doesn't imply balanced chunk *traffic*** --
   the balancer optimizes for roughly equal data volume (or chunk count)
   per shard, not equal query/write load, so a shard can hold its "fair
   share" of chunks while one specific chunk on it receives a hugely
   disproportionate fraction of actual traffic (a hot key within an
   otherwise reasonable key range).
4. **Application access pattern is itself skewed** (e.g. one large
   tenant in a multi-tenant system generating far more traffic than
   others) in a way that any single-field shard key correlating with
   that tenant will reproduce as a hot shard, independent of key
   cardinality in the abstract.

## Diagnose
- Check per-shard operation counters (`db.serverStatus().opcounters` on
  each shard's primary, or cluster-wide via `sh.status()` combined with
  per-shard monitoring) to confirm the load imbalance is about
  operations/second, not just data volume -- distinguishing this from a
  simple undersized-shard problem.
- Check chunk distribution (`sh.status()` or
  `db.collection.getShardDistribution()`) to confirm chunks are
  numerically balanced across shards -- if they are, and one shard is
  still hot, that confirms it's a traffic-concentration problem, not a
  balancer failure.
- Identify the shard key in use (`db.collection.getShardDistribution()`
  includes this, or check the collection's sharding config) and check
  its cardinality and write pattern -- specifically whether it's
  monotonically increasing (timestamps, auto-increment IDs, ObjectIds
  used directly) or low-cardinality.
- Sample recent traffic against the hot shard specifically (`db.currentOp()`
  filtered to that shard, or profiler data) to see whether load
  concentrates on a narrow key range (confirming monotonic-key hotspotting)
  or is broadly distributed but simply higher in volume (pointing toward
  a skewed-tenant or low-cardinality-key cause instead).

## Fix
- Choose a shard key with high cardinality and non-monotonic
  distribution for the dominant write pattern -- a hashed shard key
  (MongoDB's hashed sharding) on an otherwise-monotonic field
  (like `_id`) spreads writes evenly across the key space by
  hashing it first, directly addressing the monotonic-key hotspot case.
- For low-cardinality natural keys, use a compound shard key that adds a
  higher-cardinality field alongside the natural one (e.g.
  `{ tenantId: 1, _id: 1 }` or `{ country: 1, userId: 1 }`) so the
  effective key space has enough distinct values for the balancer to
  work with.
- For workload skew tied to specific key values (one large tenant), consider
  zone sharding to deliberately give a known-hot key range dedicated
  shard capacity, rather than trying to force an inherently uneven
  workload into an evenly-distributed key scheme.
- Changing a shard key on an existing large collection is a major
  operation (historically required a full reshard via dump/restore into
  a new collection; newer MongoDB versions support `reshardCollection`
  in-place) -- plan capacity and downtime/impact accordingly rather than
  treating a shard key correction as a routine schema change.

## Pitfalls
- Adding more shards without changing the shard key doesn't fix a
  monotonic-key hotspot -- new shards receive new chunks from the
  balancer, but new *writes* still concentrate on whichever shard/chunk
  currently owns the high end of the monotonically increasing key range.
- A hashed shard key fixes write distribution but makes range-based
  queries (e.g. "all documents from the last hour" on the hashed field)
  inefficient, since a range on the original field no longer maps to a
  contiguous range on any single shard -- choose the hashed field based
  on what actually needs write-distribution, and keep range queries on
  a separately-indexed field if needed.
- Confusing "balanced chunk count" in `sh.status()` with "balanced load"
  is the core misdiagnosis this skill addresses -- always check
  operation counters per shard directly, not just the balancer's chunk
  distribution report, before concluding shards are actually balanced.

## Verify
After changing the shard key (or adding zone sharding), monitor
per-shard `opcounters` under representative production write/read
volume for a full traffic cycle (including peak periods) and confirm
operation counts are roughly proportional across shards, not
concentrated on one, and confirm chunk migrations settle rather than
continuously oscillating (which would indicate an unstable key
choice).
