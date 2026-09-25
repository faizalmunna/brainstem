---
name: materialized-view-maintenance-cost-exceeds-query-savings
description: A materialized view's background refresh compute cost exceeds what it saves on read queries because it is refreshed far more often or over more data than its actual readers justify.
triggers: ["materialized view costing more than it saves", "should this be a materialized view or a regular view", "mv refresh compute expensive", "when to use materialized view vs table"]
permissions: ["READ"]
---

## Symptom
Total warehouse spend attributable to a materialized view -- its
background refresh compute plus storage -- is comparable to or higher
than what the equivalent raw query would have cost if run on demand by
its actual readers, meaning the materialization is a net cost increase
rather than the savings it was introduced to provide.

## Likely causes
1. **The materialized view refreshes on a fixed schedule regardless of
   whether it's actually queried in that window** (hourly refresh
   running around the clock for a view that's only ever queried during
   business hours a few times a day), paying refresh cost that far
   exceeds the number of reads it serves.
2. **The view materializes over the full source table on every refresh**
   (full recompute) instead of incrementally processing only new/changed
   data, so refresh cost scales with total historical data volume rather
   than with the size of the actual incremental change.
3. **The underlying query being materialized isn't actually expensive or
   frequently reused enough to justify materialization** -- it was
   materialized reflexively ("materialized views are best practice")
   without comparing against simply running it live, when the source
   data is small or the query is cheap enough that raw execution would
   have been fine.
4. **Multiple overlapping materialized views were created over time for
   slightly different but redundant purposes** (one per team, or one per
   dashboard) each independently refreshing similar underlying
   aggregations, multiplying refresh cost for largely duplicated work.

## Diagnose
- Get the materialized view's refresh compute cost (Snowflake:
  `MATERIALIZED_VIEW_REFRESH_HISTORY` credits; BigQuery: refresh job
  bytes processed in `INFORMATION_SCHEMA.JOBS` filtered to the MV's
  refresh jobs; Redshift: `STL_MV_STATE`/refresh job logs) over a
  representative period.
- Get the actual read query count and cost against that materialized
  view over the same period from query history, filtered to queries
  referencing it.
- Compare the two: if refresh cost meaningfully exceeds what the read
  queries would have cost running directly against source tables (or
  even just exceeds the reads' actual served value), the materialization
  isn't paying for itself.
- Check whether the refresh mechanism is full vs. incremental (engine-
  specific: Snowflake materialized views maintain incrementally
  automatically for supported query shapes; check whether the view's
  query pattern actually qualifies, since some constructs fall back to
  full recompute silently).
- Check for other materialized views/tables with substantially
  overlapping source tables and aggregation logic that might be
  consolidatable.

## Fix
Match refresh cadence to actual read frequency and the documented
freshness SLA rather than a default schedule -- reduce refresh frequency
for views read rarely or only during specific hours, potentially
switching to on-demand/triggered refresh instead of a fixed interval.
Prefer engine features that support genuine incremental maintenance for
the view's query shape, and if the query pattern doesn't qualify for
incremental refresh (falls back to full recompute), consider whether a
regular table with an explicit incremental `MERGE`/`INSERT` transformation
job would be cheaper and more predictable than relying on the
materialized view mechanism. For low-value materializations, simply
un-materialize back to a plain view or on-demand query when testing
shows the read savings don't justify refresh cost. Consolidate redundant
overlapping materialized views into one shared one where their
underlying aggregation logic is genuinely the same.

## Pitfalls
Don't decide to un-materialize based only on average-case read cost --
a materialized view can be net-negative on average while still being
essential for a specific latency-sensitive peak-load consumer (e.g. a
support dashboard that must load in under a second during an incident);
check who actually depends on the view's speed, not just aggregate cost,
before removing it. Also, incremental refresh isn't automatically
cheaper in every case -- a view whose underlying data changes almost
entirely between refreshes (e.g. a full daily reload of the source
table) gets little benefit from incremental logic and may be simpler and
just as cheap as a straightforward full refresh.

## Verify
After adjusting refresh cadence or mechanism, compare total attributable
cost (refresh compute plus storage) against read-query cost saved over a
full subsequent billing cycle, and confirm the balance has shifted toward
net savings. Confirm no consumer's freshness requirement was violated by
checking actual observed staleness against the documented SLA after the
change.
