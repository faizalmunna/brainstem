---
name: bi-dashboard-recomputes-query-per-viewer-instead-of-cache
description: A BI dashboard re-executes its expensive underlying warehouse query for every individual viewer instead of reusing a cached or materialized result, multiplying compute cost with viewer count.
triggers: ["dashboard costs scale with number of viewers", "bi tool re-running same query for every user", "looker tableau query cost multiplying", "dashboard load triggers full warehouse query every time"]
permissions: ["READ"]
---

## Symptom
Warehouse compute cost or query volume for a specific dashboard scales
roughly linearly with how many people view it (or how often it's
auto-refreshed), even though the underlying data and query are identical
for every viewer -- ten people opening the same dashboard in the same
hour triggers roughly ten full executions of the same expensive query.

## Likely causes
1. **The BI tool is configured to always query live** (a "live"/"direct
   query" connection mode) rather than using its own result cache or a
   scheduled extract, so every page load or filter interaction issues a
   fresh query against the warehouse regardless of whether the
   underlying data changed since the last viewer's load.
2. **The dashboard's cache TTL is shorter than the actual data refresh
   cadence**, so cache misses happen far more often than the data
   actually changes -- effectively paying for live-query cost while
   gaining none of the freshness benefit that would justify it.
3. **Per-user row-level security or personalized filters are implemented
   in a way that makes every viewer's query technically unique** (a
   user-ID filter baked into the query text itself rather than applied
   as a lightweight post-cache filter), which defeats result caching even
   when the tool supports it, because the cache key never matches between
   users.
4. **Auto-refresh interval on an embedded/TV-mode dashboard is set too
   aggressively** (e.g. refreshing every minute for data that updates
   hourly), independent of viewer count, compounding the multiplication
   effect from concurrent viewers.

## Diagnose
- Check the BI tool's connection mode for the dashboard's data source
  (live/direct query vs. extract/cached) -- most tools expose this
  explicitly per dashboard or per data source.
- Query the warehouse's query history filtered by the BI tool's service
  account/user and the specific SQL text (or a hash/fingerprint of it) to
  count how many times the identical query ran in a given window, and
  correlate against dashboard view analytics (if the BI tool tracks
  views) to confirm the 1:1 (or worse) ratio.
- Check the dashboard's configured cache TTL/extract refresh schedule
  against how frequently the underlying source table actually updates --
  a mismatch in either direction (too tight a cache, or stale beyond
  tolerance) is diagnosable directly from these two numbers.
- If row-level security is involved, inspect the actual generated SQL
  per user (via query history) to see whether the security filter is
  embedded in the query text (breaks caching) vs. applied at a layer
  above a shared cached result.

## Fix
Switch the dashboard to the BI tool's cached/extract query mode where
live-to-the-second freshness isn't actually required, with a cache TTL
matched to the real freshness SLA (see the materialized-view-refresh
staleness skill for how to determine that number) rather than left at a
tool default. For dashboards that must reflect near-real-time data,
push the expensive aggregation into a materialized view or scheduled
summary table so the dashboard's live query hits a small pre-aggregated
result instead of recomputing from raw fact tables on every load. Where
per-user personalization is required, structure it so the expensive
shared computation is cached once and the cheap per-user filter is
applied on top of the cached result, rather than baking the per-user
condition into the query that hits the warehouse.

## Pitfalls
Switching to a cached/extract mode without checking the tool's cache
invalidation behavior can silently reintroduce the staleness problem
this fix was meant to trade against -- confirm the cache actually
refreshes on the intended schedule rather than only on manual trigger.
Also, don't assume every dashboard should be cached: a genuinely
low-traffic, genuinely-needs-live-data operational dashboard may be
correctly configured as live query, and forcing a cache there trades
real value (freshness) for a cost saving that doesn't apply at low
viewer counts.

## Verify
After the change, compare warehouse query history volume for that
dashboard's queries before and after over a period with similar viewer
traffic, and confirm query count no longer scales with viewer count
(ideally flat, bounded by the cache refresh cadence rather than by
views). Confirm dashboard viewers don't perceive data as stale beyond
the documented freshness SLA.
