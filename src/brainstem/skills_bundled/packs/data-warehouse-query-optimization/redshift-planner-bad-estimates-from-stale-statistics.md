---
name: redshift-planner-bad-estimates-from-stale-statistics
description: Redshift query performance degrades gradually over weeks because table statistics are stale and the query planner picks bad join and scan strategies from wrong row estimates.
triggers: ["redshift query got slower over time", "redshift bad query plan", "analyze command redshift", "redshift row estimate way off", "redshift performance degrading gradually"]
permissions: ["READ"]
---

## Symptom
A Redshift query (or a whole ETL job) that used to run in a predictable
amount of time has gradually gotten slower over days or weeks with no
corresponding code change or data-volume shock -- it isn't a sudden
regression tied to a deploy, it's a slow drift, and re-running the exact
same query with no other changes sometimes fixes it.

## Likely causes
1. **Table statistics are stale because `ANALYZE` hasn't run recently
   (or `STATUPDATE` is off) after significant insert/update/delete
   volume**, so the planner's row-count estimates no longer reflect
   reality and it chooses join orders, distribution strategies, or scan
   methods appropriate for the old, smaller/differently-shaped data.
2. **Redshift's automatic analyze (if relying on it) has a threshold for
   how much a table must change before it re-analyzes**, and a table
   that grows via many small incremental loads (rather than one big
   bulk load) can drift substantially before crossing that threshold.
3. **Table is unsorted or has a high percentage of unsorted rows**
   (`VACUUM` hasn't run, or is running but not keeping up with insert
   volume), which independently degrades scan performance regardless of
   statistics accuracy, and is often conflated with a stats problem
   because both present as "got slower over time."
4. **A query pattern changed slightly** (a new filter value distribution,
   a newly-common `WHERE` value that used to be rare) that interacts
   badly with an already-marginal plan choice that stale statistics made
   look fine.

## Diagnose
- Run `SELECT * FROM svv_table_info WHERE stats_off > 10` (or the current
  equivalent system view) to find tables where Redshift's own tracked
  "percent stats off" indicates the optimizer's statistics have drifted
  significantly from actual data.
- Run `EXPLAIN` on the slow query and compare estimated vs. actual rows
  via `EXPLAIN ANALYZE`-equivalent tooling (Redshift's query plan plus
  `SVL_QUERY_SUMMARY`/`SVL_QUERY_REPORT` for actual row counts per step)
  -- a large estimate-vs-actual gap at a specific join or scan step
  points at stale stats for that table.
- Check `svv_table_info` for `unsorted` percentage on the tables
  involved -- a high unsorted percentage points at a vacuum problem
  layered on top of (or instead of) a stats problem.
- Check when `ANALYZE` last ran per table (via query history for
  `ANALYZE`/`VACUUM` statements, or `svv_table_info.stats_off` combined
  with load job timestamps) to correlate degradation onset with the last
  successful statistics update.

## Fix
Run `ANALYZE` on affected tables to refresh planner statistics, and set
up a recurring `ANALYZE` (either via Redshift's automatic analyze,
tuned appropriately, or an explicit scheduled job after major load
batches) rather than relying on ad hoc manual runs triggered only after
someone notices degradation. Pair this with routine `VACUUM` (or rely on
automatic table sort/vacuum where available) so physical row order
stays close to the sort key and scans don't degrade independently of
statistics accuracy. For tables loaded via frequent small increments
rather than large bulk loads, explicitly schedule `ANALYZE` after a
cadence of accumulated change (e.g. daily) rather than depending on an
automatic threshold that may not trigger promptly under a slow-drip
load pattern.

## Pitfalls
Running `ANALYZE` on very large tables indiscriminately and frequently
has its own non-trivial compute cost -- prefer `ANALYZE` with a specific
column list matching actual predicate/join usage, or use Redshift's
predicate-based incremental analyze, rather than a blanket full-table
`ANALYZE` on every table on every schedule tick. Also, don't assume a
fresh `ANALYZE` alone fixes a plan that's actually degraded because of
unsorted rows -- if `VACUUM` hasn't run, statistics can be accurate while
the physical scan is still slow, and treating this as purely a
stats problem will look like the fix "didn't work."

## Verify
After running `ANALYZE` (and `VACUUM` if needed), re-run `EXPLAIN` and
confirm the estimated row counts now closely match actual row counts
from a subsequent execution, and confirm `svv_table_info.stats_off` has
dropped for the affected tables. Track the query's execution time over
the following weeks to confirm the degradation trend doesn't recur, and
verify the scheduled `ANALYZE`/`VACUUM` cadence is actually running
(check job history, not just that it's configured).
