---
name: bigquery-query-cost-explosion-full-scan
description: A BigQuery bill spikes because queries scan entire tables instead of the partitioned or clustered subset actually needed, billed by bytes scanned.
triggers: ["bigquery bill too high", "bigquery full table scan cost", "bigquery query scanning too much data", "bigquery partition not being used"]
permissions: ["READ"]
---

## Symptom

A BigQuery billing report shows a sharp increase in query costs (billed
on-demand pricing is based on bytes scanned) without a corresponding
increase in actual query volume or business need -- individual queries
that seem like they should be cheap and targeted are actually scanning
far more data than expected.

## Likely causes

- **A table is partitioned (commonly by date) but a query's `WHERE`
  clause doesn't filter on the partitioning column in a way BigQuery can
  use for partition pruning** -- e.g. applying a function to the
  partitioning column that prevents pruning, or filtering on a different,
  correlated but not identical column.
- **A query selects `SELECT *`** when only a few columns are actually
  needed -- BigQuery's columnar storage means cost scales with columns
  scanned, not just rows, so unnecessary columns directly inflate cost.
- **A table meant to be clustered isn't actually clustered on the columns
  most commonly filtered on**, so even column-pruning-aware queries still
  scan more data blocks than necessary for a given filter.
- **A join or subquery structure causes BigQuery to scan a large table
  multiple times**, or a query pattern (a correlated subquery per row)
  multiplies scan cost in a way that's not obvious from reading the SQL
  casually.

## Diagnose

1. Use BigQuery's query validator/dry-run feature (or the query
   execution details after running) to see exactly how many bytes a
   specific query scanned, before optimizing based on assumption.
2. Check the query execution plan for whether partition pruning
   actually occurred -- BigQuery's query plan explicitly shows whether
   partitions were pruned or a full table was scanned.
3. Identify the specific queries (via BigQuery's own query history/audit
   logs, sorted by bytes billed) responsible for the largest share of
   recent cost, rather than guessing which ones are expensive.
4. For the worst offenders, check for `SELECT *`, unfiltered or
   filter-not-on-partition-column patterns, and joins/subqueries against
   large unclustered tables.

## Fix

Rewrite queries to filter directly and simply on the partitioning column
(avoiding functions/transformations on it that prevent pruning), and
select only the specific columns actually needed rather than `SELECT *`.
Add clustering to tables on the columns most frequently used in filters,
if not already clustered appropriately. For recurring expensive query
patterns, consider materializing a smaller, pre-aggregated or
pre-filtered table that the frequent queries can hit instead of scanning
the full source table each time. Where budget predictability matters
more than per-query optimization effort, consider BigQuery's flat-rate/
capacity-based pricing instead of on-demand for high-volume, well-
understood workloads.

## Pitfalls

Don't over-partition or over-cluster a table in a way that creates too
many small partitions/blocks, which can itself add overhead and doesn't
help (or can hurt) query performance and cost -- partition/cluster
granularity should match actual query filter patterns, not be maximized
blindly. Also don't assume every `SELECT *` needs immediate fixing
without checking whether the specific table actually has many columns --
the cost impact scales with actual column count and data volume, so
prioritize the highest-cost queries first.

## Verify

Re-run the optimized queries with dry-run/bytes-scanned estimation and
confirm a significant reduction compared to the original versions.
Monitor the overall BigQuery billing trend over the following billing
cycle to confirm the optimization translates into an actual cost
reduction, not just a smaller number for the specific queries tested.
