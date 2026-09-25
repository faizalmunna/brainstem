---
name: snowflake-warehouse-idle-billing-no-auto-suspend
description: A Snowflake virtual warehouse keeps billing per-second compute credits long after the last query finished because auto-suspend is disabled or set too high.
triggers: ["snowflake warehouse billing too much when idle", "snowflake credits burning with no queries running", "auto-suspend not working snowflake", "warehouse still running after query finished"]
permissions: ["READ"]
---

## Symptom
A Snowflake warehouse shows up in `WAREHOUSE_METERING_HISTORY` as consuming
credits during long stretches with no query activity, or the account's
monthly credit spend is far higher than the actual query workload would
suggest -- the warehouse appears to just be "left on."

## Likely causes
1. **Auto-suspend is disabled or set to an unnecessarily long interval**
   (the default when created via some client tools/ORMs is sometimes much
   higher than needed, e.g. 10+ minutes), so the warehouse keeps billing
   for the full idle window after every query, not just active compute
   time.
2. **A BI tool or orchestrator holds a persistent connection/session
   open** (connection pooling that never closes), which some monitoring
   naively treats as "still in use," effectively resetting the idle timer
   and preventing suspension even when no query is actually running.
3. **Auto-resume is enabled but a scheduled or polling job queries the
   warehouse every few minutes** (a health check, a dashboard
   auto-refresh, a dbt job scheduled far more frequently than needed),
   so the warehouse never stays idle long enough to hit the suspend
   threshold even though it's correctly configured.
4. **Multi-cluster warehouse scaling policy keeps extra clusters warm**
   ("Economy" vs. default scaling policy misconfigured, or min clusters
   set above 1) so idle *additional* clusters bill even while the
   baseline cluster is appropriately suspending.

## Diagnose
- Run `SHOW WAREHOUSES` and check the `auto_suspend` column (in seconds)
  and `auto_resume` for every warehouse -- flag any with auto-suspend
  disabled (`NULL`/0) or set above a few hundred seconds for workloads
  that aren't latency-sensitive.
- Query `SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` joined
  against `QUERY_HISTORY` for the same warehouse and time window to find
  gaps where credits were billed but no query ran -- that gap length
  should roughly match (or exceed) the configured auto-suspend interval
  if it's working correctly.
- Check `QUERY_HISTORY` for the querying client/user driving apparent
  "keep-alive" traffic (frequent trivial queries like `SELECT 1` or
  metadata pings) that would reset the idle timer.
- For multi-cluster warehouses, check `MIN_CLUSTER_COUNT` and
  `SCALING_POLICY` in `SHOW WAREHOUSES` -- a `MIN_CLUSTER_COUNT` above 1
  keeps that many clusters warm regardless of auto-suspend.

## Fix
Set `AUTO_SUSPEND` to the shortest interval that doesn't cause excessive
resume-latency pain for the actual workload -- 60 seconds is a reasonable
default for ad hoc/BI warehouses since Snowflake's resume time is
typically a few seconds, and the credit cost of staying idle for minutes
"just in case" almost always outweighs the resume latency cost. For
warehouses serving latency-sensitive interactive dashboards where even a
few seconds of resume lag is unacceptable, that's a deliberate tradeoff
to document, not an oversight -- keep auto-suspend short elsewhere and
isolate that one warehouse. Identify and fix the source of keep-alive
polling (reduce dashboard auto-refresh frequency, close idle pooled
connections, or route health checks to a dedicated tiny warehouse that
suspends aggressively) so the warehouse can actually reach its idle
threshold. For multi-cluster warehouses, set `MIN_CLUSTER_COUNT = 1`
unless sustained concurrent load genuinely requires a warm floor above
one cluster.

## Pitfalls
Setting auto-suspend extremely low (e.g. a few seconds) on a warehouse
that serves bursty-but-frequent interactive queries can cause constant
suspend/resume cycling, and while resume is fast it isn't free or
instant -- this can paradoxically hurt perceived latency for users
without meaningfully reducing cost if queries are frequent enough that
the warehouse would rarely have suspended anyway. Tune the interval to
the actual query arrival pattern, not to zero by default.

## Verify
After changing `AUTO_SUSPEND`, query
`SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY` for that warehouse
over the following few days and confirm credit consumption now tracks
actual query activity windows (idle gaps no longer bill), and compare
total daily credits before and after the change to confirm a measurable
reduction with no complaints about resume latency from warehouse users.
