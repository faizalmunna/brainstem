---
name: clustering-key-chosen-for-ingestion-not-query-pattern
description: A table's clustering or partitioning key was chosen for ingestion convenience like load timestamp rather than actual query filters, so most queries get no partition pruning.
triggers: ["partition pruning not working", "clustering key not helping queries", "table partitioned wrong", "queries still scanning full table despite partitioning"]
permissions: ["READ"]
---

## Symptom
A table is partitioned or clustered (on Snowflake, BigQuery, or
Redshift's equivalent sort keys), yet query profiles consistently show
most or all partitions/micro-partitions being scanned regardless of the
query's `WHERE` clause -- the partitioning exists on paper but isn't
actually reducing scan volume for the queries people run against it day
to day.

## Likely causes
1. **The partition/clustering key was set to the ingestion or load
   timestamp** (when the row was written into the warehouse) because
   that was the simplest column available at load time, but downstream
   queries actually filter on a business-meaningful event timestamp or
   dimension (e.g. `order_date`, `customer_region`) that differs from
   load time and isn't correlated with it in a way that helps pruning.
2. **The table was partitioned by the column easiest to derive from the
   source system** (e.g. an auto-incrementing surrogate key or an
   ingestion batch ID) rather than by profiling actual downstream query
   `WHERE`/`JOIN` predicates before choosing.
3. **Query patterns evolved after the clustering key was chosen** -- the
   table was originally queried mostly by date, clustering was set
   accordingly, but the dominant use case shifted to filtering by another
   dimension (customer, region, product) without anyone revisiting the
   physical layout.
4. **A composite clustering key's column order doesn't match the most
   selective or most commonly-filtered-alone column first**, so queries
   filtering only on the second or third clustering column get little to
   no pruning benefit even though clustering nominally includes that
   column.

## Diagnose
- Pull the most frequent/most expensive query patterns against the table
  from query history (grouped by normalized query text or filter
  columns), and list which columns actually appear in their `WHERE`
  clauses.
- Compare that list against the table's actual partition/clustering key
  definition (BigQuery: `INFORMATION_SCHEMA.TABLES` partitioning/
  clustering columns; Snowflake: `SYSTEM$CLUSTERING_INFORMATION`;
  Redshift: sort key via `PG_TABLE_DEF`/`SVV_TABLE_INFO`).
- For a specific representative slow query, check the query
  plan/profile's pruning statistics directly -- BigQuery shows
  partitions processed vs. total; Snowflake's
  `SYSTEM$CLUSTERING_INFORMATION` and query profile show
  partitions scanned; Redshift shows scanned rows relative to table size
  in `SVL_QUERY_SUMMARY`.
- If clustering exists but pruning is poor, check
  `SYSTEM$CLUSTERING_INFORMATION` (Snowflake) for a high average
  overlap/depth value, which indicates the table's physical layout has
  drifted from the clustering key's ideal grouping (common after heavy
  updates/deletes) even if the key choice itself is reasonable.

## Fix
Re-derive the partition/clustering key from actual observed query filter
patterns (the most common and most selective `WHERE`/`JOIN` columns),
not from whichever column was most convenient at load time. Where the
dominant filter is a business timestamp different from load time,
partition/cluster on the business timestamp even if it requires deriving
or backfilling it during transformation. For composite keys, order
columns from most to least commonly filtered alone, matching actual
query predicate frequency. Where query patterns have genuinely
diversified across multiple unrelated dimensions with no single dominant
filter, consider maintaining a second differently-clustered copy or
materialized view for the minority pattern rather than compromising the
primary table's layout for everyone.

## Pitfalls
Re-clustering or re-partitioning a large existing table is itself an
expensive, disruptive operation (a full rewrite in most engines) --
don't do it reactively for every minor query-pattern shift; batch the
decision against a reasonably stable read of query patterns over weeks,
not a single recent complaint. Also, don't choose a partition/clustering
key with too many distinct values relative to table size (e.g.
partitioning by a near-unique ID) -- this creates excessive small
partitions that add metadata overhead without meaningfully improving
pruning, the opposite failure mode from choosing too coarse a key.

## Verify
After re-clustering/re-partitioning, re-run the representative queries
identified during diagnosis and confirm partition/micro-partition pruning
statistics show a substantial reduction in scanned partitions relative to
total, and confirm overall bytes scanned or query latency improved
correspondingly under real query volume, not just the sample query used
for diagnosis.
