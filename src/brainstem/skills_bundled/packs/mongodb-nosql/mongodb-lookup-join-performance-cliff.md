---
name: mongodb-lookup-join-performance-cliff
description: Diagnose a $lookup aggregation stage performing far worse than expected because MongoDB is being used for relational-style joins at scale.
triggers: ["$lookup is really slow", "aggregation with lookup taking forever", "mongodb join performance bad", "lookup stage timing out", "why is $lookup so much slower than a sql join"]
permissions: ["READ"]
---

## Symptom
An aggregation pipeline using `$lookup` to join two collections performs
acceptably in development or at small data volume, then becomes
dramatically slower -- sometimes by orders of magnitude -- as either
collection grows, or when the joined ("foreign") collection lacks an
index on the join field. Latency and resource usage for a single
"simple join" query can rival or exceed a full collection scan, which
surprises teams coming from a relational background where joins are
core, heavily-optimized functionality.

## Likely causes
1. **No index on the foreign collection's `foreignField`** -- `$lookup`
   performs, conceptually, a query against the foreign collection for
   each distinct value of `localField` in the input; without an index on
   `foreignField`, each of those lookups is a collection scan, and the
   cost multiplies by the number of distinct input values.
2. **The simple (non-pipeline) `$lookup` form joins on equality only and
   materializes all matches before any further filtering**, so a join
   that could have been narrowed with additional conditions instead
   pulls in every matching foreign document first, wasting work when
   only a subset would ultimately be needed.
3. **`$lookup` used for a relationship that's fundamentally many-to-many
   or high-fan-out** (each local document matching a large number of
   foreign documents), which produces a large intermediate result the
   pipeline then has to process further -- a shape relational databases
   handle with optimized join algorithms and statistics-driven planning
   that MongoDB's aggregation engine doesn't replicate.
4. **Joining across a sharded collection** -- `$lookup` against a
   sharded foreign collection has historically had more limited
   optimization than joining unsharded collections (requiring the
   operation to fan out across shards), making it meaningfully more
   expensive than the equivalent join would be in a single-node
   relational database.
5. **Schema design defaulted to normalization (separate collections
   joined at query time) out of relational habit**, when the actual
   access pattern would have been well served by embedding or
   denormalizing at write time -- the join being slow is a symptom of
   a schema decision, not just a query-tuning problem.

## Diagnose
- Run `.explain("executionStats")` on the pipeline and inspect the
  `$lookup` stage's own stats (newer MongoDB versions report
  sub-stage execution stats within `$lookup`) for whether it used an
  index on the foreign collection or performed a collection scan per
  lookup.
- Check `db.foreignCollection.getIndexes()` for an index on the field
  used as `foreignField` -- its absence is the single most common and
  most directly fixable cause.
- Check the fan-out ratio: for a sample of local documents, how many
  foreign documents does each one match on average and at the high end
  -- a high or highly variable fan-out (some local documents matching
  thousands of foreign documents) explains a slow, memory-heavy
  `$lookup` independent of indexing.
- Compare latency at current data volume against latency at a
  meaningfully smaller volume (a staging snapshot or historical
  baseline) -- confirm whether the slowness is roughly proportional to
  foreign collection size (pointing to missing index) or to fan-out
  per document (pointing to relationship cardinality) to distinguish
  the two root causes.

## Fix
- Add an index on the foreign collection's `foreignField` -- this alone
  frequently resolves the most severe cases, turning a per-lookup
  collection scan into an index seek.
- Use the pipeline-style `$lookup` (with `let` and an inner `pipeline`
  containing its own `$match`/`$limit`) to filter and bound the foreign
  side of the join before it's materialized, rather than pulling every
  matching document and filtering afterward.
- For a relationship that's queried together far more often than it
  changes, consider denormalizing (embedding a copy of the needed
  foreign fields into the local document, updated on write) instead of
  joining at read time -- this trades write-time complexity for
  read-time simplicity, which is usually the right trade for read-heavy
  access patterns.
- Reconsider whether the relationship needs a real-time join at all --
  for reporting/analytics-style joins, materializing a precomputed,
  periodically refreshed joined view (via a scheduled aggregation or
  change-stream-driven projection) can avoid paying join cost on every
  read.
- If joining sharded collections is unavoidable and slow, check whether
  restructuring the shard key or query to target a single shard (or a
  small number of shards) per lookup reduces the cross-shard fan-out
  cost.

## Pitfalls
- Treating `$lookup` as a drop-in equivalent for a SQL join and
  expecting comparable optimization -- MongoDB's aggregation engine
  doesn't have the decades of join-specific query planning (hash joins,
  merge joins, cost-based join reordering) that mature relational
  engines do; design around that reality rather than assuming
  performance parity.
- Denormalizing to avoid `$lookup` without a clear plan for keeping the
  duplicated data in sync introduces the same staleness risk discussed
  in cache-invalidation-style problems -- decide explicitly what updates
  the denormalized copy and how quickly it needs to reflect source
  changes.
- Adding the foreign-field index but not checking fan-out -- a query
  can be "using the index" and still be slow/memory-heavy if it matches
  an enormous number of foreign documents per local document; the two
  causes require different fixes and it's easy to fix one and declare
  victory while the other remains.

## Verify
Re-run `.explain("executionStats")` on the pipeline and confirm the
`$lookup` stage now uses an index on the foreign collection, then
measure end-to-end pipeline latency at production-representative data
volume and fan-out (not a small dev dataset) and confirm it meets the
actual latency requirement for how the result is consumed (real-time
request vs. batch report).
