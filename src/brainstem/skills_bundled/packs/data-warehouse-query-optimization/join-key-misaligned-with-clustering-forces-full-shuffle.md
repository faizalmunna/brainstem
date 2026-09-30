---
name: join-key-misaligned-with-clustering-forces-full-shuffle
description: A join between two large warehouse tables runs far slower than expected because the join keys don't match either table's clustering, sort, or distribution key.
triggers: ["join is slow on two large tables", "why is this join scanning everything", "redshift broadcast join too expensive", "snowflake join shuffling too much data", "distkey mismatch slow join"]
permissions: ["READ"]
---

## Symptom
A query joining two large fact/dimension-scale tables takes minutes
instead of seconds, and the query profile/explain plan shows most of the
time spent in a shuffle, broadcast, or redistribution step rather than in
the actual filter or aggregation logic -- the join itself, not downstream
processing, dominates runtime and (on Snowflake/BigQuery) bytes
processed.

## Likely causes
1. **Redshift table distribution style (`DISTSTYLE`/`DISTKEY`) doesn't
   match the join column**, forcing Redshift to redistribute one or both
   tables' rows across nodes at query time (a network-shuffle join)
   instead of performing a fast co-located join.
2. **Snowflake or BigQuery table clustering/partitioning key doesn't
   include or align with the join predicate column**, so the engine can't
   prune micro-partitions/blocks on either side of the join before the
   join executes, and ends up scanning and shuffling far more rows than
   the logical result requires.
3. **A join key's data type or representation differs between the two
   tables** (e.g. a string `customer_id` on one side and a numeric
   `customer_id` on the other, or inconsistent casing/whitespace),
   silently defeating any distribution-key or clustering alignment even
   if the key names match, since the optimizer treats them as
   incompatible without an implicit or explicit cast.
4. **One table is small enough to broadcast but the optimizer chooses a
   shuffle join anyway** because stale table statistics understate its
   actual current size, or it has grown past the broadcast threshold
   without anyone revisiting the join strategy.

## Diagnose
- Redshift: run `EXPLAIN` and look for `DS_BCAST_INNER`/`DS_DIST_BOTH`/
  `DS_DIST_NONE` labels on the join step -- `DS_DIST_NONE` means data was
  already co-located (good); the others indicate redistribution or
  broadcast cost. Cross-check with `SVL_QUERY_SUMMARY` for the join
  step's actual row counts and time.
- Compare each table's `DISTKEY` (via `SVV_TABLE_INFO` or `PG_TABLE_DEF`
  on Redshift) against the actual join predicate columns used in the
  slow query.
- Snowflake: use the query profile's join operator node and check
  "bytes scanned" and "partitions scanned vs. total" for each input --
  a high scanned-to-total ratio on a clustered table during a join
  indicates the clustering key isn't helping this specific join.
- Check both tables' join-column data types (`information_schema.columns`
  or `DESCRIBE TABLE`) for a type or collation mismatch that would force
  an implicit cast.
- Check when table statistics were last collected (Redshift:
  `SVV_TABLE_INFO.stats_off`; BigQuery/Snowflake: row count metadata
  used by the optimizer) to rule out a stale-stats-driven broadcast
  decision.

## Fix
Align the physical data layout with the actual join pattern: on Redshift,
set `DISTKEY` on the column(s) most frequently used to join large tables
together (or use `DISTSTYLE ALL` only for genuinely small, rarely-updated
dimension tables) so matching rows are already co-located and no network
shuffle is needed. On Snowflake/BigQuery, choose a clustering/partitioning
key that includes the common join column when that column is also a
common filter, so pruning happens on both sides consistently. Normalize
join-key types and formatting (cast once during ingestion/transformation
rather than per-query) so the optimizer can rely on a clean equality
predicate. When the join pattern genuinely varies across many different
key combinations, accept that no single physical layout serves all of
them and instead pre-aggregate or pre-join the highest-frequency pattern
into a dedicated table.

## Pitfalls
Choosing a distribution or clustering key based on the single slowest
query without checking how that same table is joined or filtered
elsewhere can fix one query while degrading several others -- audit the
table's actual query patterns (via query history) before committing to a
new key, since redistributing a large table is itself an expensive,
disruptive operation. Also, don't assume `DISTSTYLE ALL` is free: it
duplicates the full table onto every node, which is fine for a small
dimension table but will blow up storage and slow every write if applied
to a table that's actually large or frequently updated.

## Verify
Re-run the join with `EXPLAIN`/query profile and confirm the
redistribution/broadcast step is gone or now operates on a much smaller
row count (ideally `DS_DIST_NONE` on Redshift, or a high partition-pruned
ratio on Snowflake/BigQuery), and measure wall-clock query time and
bytes/data scanned before and after under representative production data
volume, not a small sample.
