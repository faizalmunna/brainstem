---
name: etl-and-adhoc-queries-contend-on-shared-compute-pool
description: Interactive ad hoc queries and scheduled ETL jobs queue up and slow each other down because they share one compute resource pool with no workload isolation.
triggers: ["queries queuing during etl", "dashboard slow during batch load", "redshift wlm queue full", "snowflake queries waiting for warehouse", "analysts complaining etl slows them down"]
permissions: ["READ"]
---

## Symptom
Analysts or dashboard users report queries running noticeably slower (or
visibly queuing) at specific times of day, and those times correlate with
scheduled ETL/batch job windows -- a heavy nightly load or transformation
job monopolizes the same compute resource that interactive users are
also trying to use, and both workloads degrade each other unpredictably.

## Likely causes
1. **A single Redshift cluster with one default WLM (workload management)
   queue** serves both long-running batch ETL statements and short
   interactive queries, so a handful of heavy ETL queries can consume
   most available query slots/memory and force interactive queries to
   queue behind them.
2. **A single Snowflake warehouse is shared across ETL and BI/ad hoc
   use** rather than provisioning separate warehouses per workload type,
   so a large ETL query on that warehouse competes for the same compute
   as concurrent interactive queries, and one workload's usage pattern
   (bursty ETL) doesn't match the other's (steady interactive), making
   sizing for either poorly serve both.
3. **No query prioritization or resource governance is configured at
   all** (Redshift WLM queues left at default, Snowflake resource
   monitors/warehouses undifferentiated by workload), so there's no
   mechanism to prevent one runaway or inefficient query from starving
   others regardless of which workload it belongs to.
4. **Auto-scaling (Snowflake multi-cluster, Redshift concurrency scaling)
   isn't enabled or is capped too low**, so genuine concurrent demand
   from both workloads at peak times exceeds available compute with no
   automatic relief valve.

## Diagnose
- Redshift: check `STV_WLM_QUERY_STATE` / `SVL_QUERY_QUEUE_INFO` for
  queries that spent significant time queued (not executing) and
  correlate queue timestamps with known ETL job schedules.
- Snowflake: query `WAREHOUSE_LOAD_HISTORY` for the shared warehouse and
  look for periods of high `AVG_RUNNING`/`AVG_QUEUED_LOAD` overlapping
  known ETL job run times; check `QUERY_HISTORY` for
  `EXECUTION_STATUS = 'QUEUED'`... time on interactive queries during
  those windows.
- Check whether separate WLM queues (Redshift) or separate warehouses
  (Snowflake) even exist for different workload types, or whether
  everything currently routes through one shared queue/warehouse.
- Check current WLM queue concurrency/memory allocation settings
  (Redshift) or warehouse size and multi-cluster scaling policy
  (Snowflake) against actual peak concurrent query counts by workload
  type.

## Fix
Separate workloads onto isolated compute: on Redshift, configure
distinct WLM queues (or use automatic WLM with query priority) so ETL
and interactive queries don't compete for the same concurrency slots,
assigning ETL to a queue sized for fewer, longer-running statements and
interactive to a queue tuned for many short, latency-sensitive ones. On
Snowflake, provision separate warehouses per workload type (an ETL
warehouse, a BI warehouse, an ad hoc analyst warehouse), each sized and
auto-suspended independently for its own usage pattern, since compute
isolation in Snowflake is warehouse-level, not a shared-cluster queue.
Enable and appropriately cap auto-scaling (concurrency scaling on
Redshift, multi-cluster warehouses on Snowflake) so genuine peak
concurrent demand within a workload gets relief without manual
intervention, rather than either starving queries or requiring a
permanently oversized baseline.

## Pitfalls
Splitting workloads onto separate compute without also right-sizing each
one can just relocate the cost problem -- a dedicated ETL warehouse sized
far larger than its actual batch workload needs still wastes money even
though it's no longer blocking analysts. Also, over-segmenting into many
narrow warehouses/queues for every team or use case fragments visibility
and can multiply idle-but-billing surface area (see the auto-suspend
skill) -- isolate by genuinely different workload *shape* (batch vs.
interactive), not by every organizational boundary.

## Verify
After separating workloads, check queue/queued-load metrics again during
the next scheduled ETL run and confirm interactive queries no longer show
significant queued time during that window. Collect user-reported latency
feedback (or dashboard load-time metrics) for the period following the
change and confirm no regression during concurrent ETL execution.
