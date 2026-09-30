---
name: snowflake-warehouse-oversized-for-actual-workload
description: A Snowflake warehouse is sized much larger than the query workload requires, burning credits on unused compute capacity rather than actually speeding up queries.
triggers: ["snowflake warehouse too big", "should I downsize snowflake warehouse", "snowflake credits high but queries not faster", "what size warehouse do I need snowflake"]
permissions: ["READ"]
---

## Symptom
A Snowflake warehouse is running at a size (e.g. Large or X-Large) that
was chosen defensively ("just in case") or copied from another team's
config, and query performance doesn't noticeably degrade when tested at
a smaller size -- credits billed per second scale directly with
warehouse size, so an oversized warehouse burns significantly more
credit per query-second than needed without a proportional speed benefit
for the actual workload running on it.

## Likely causes
1. **The warehouse size was chosen once for a specific heavy workload
   (a large backfill, a big migration) and never downsized afterward**
   once that one-time job completed, leaving routine day-to-day queries
   running on oversized compute indefinitely.
2. **Warehouse size was picked to "be safe" without load-testing smaller
   sizes**, on the mistaken assumption that bigger always means
   meaningfully faster -- for many query shapes (small-to-moderate scan
   volume, low concurrency), a larger warehouse reduces latency
   negligibly because the bottleneck isn't raw compute parallelism.
3. **Concurrency, not per-query speed, is the actual problem**, and the
   team scaled warehouse *size* (vertical) to address what was really a
   concurrency/queuing issue that multi-cluster warehouses (horizontal
   scaling) or query prioritization would address more cost-effectively.
4. **Different query types with very different resource needs share one
   warehouse sized for the heaviest of them**, so lightweight queries pay
   the oversized warehouse's per-second rate even though they'd run
   nearly as fast on a much smaller warehouse.

## Diagnose
- Query `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` for the warehouse and
  look at `EXECUTION_TIME` distribution alongside `WAREHOUSE_SIZE` --
  if most queries complete quickly and don't show scan/compute-bound
  profiles (check `BYTES_SCANNED` and `PARTITIONS_SCANNED` relative to
  execution time), the workload may not need the current size at all.
- Check for queuing (`QUEUED_PROVISIONING_TIME`/`QUEUED_OVERLOAD_TIME` in
  `QUERY_HISTORY`) -- if queuing is the actual pain point rather than
  per-query execution time, the fix is concurrency (multi-cluster) not
  size.
- Temporarily test a smaller warehouse size against a representative
  sample of the actual production query mix (Snowflake allows resizing
  without data movement) and compare execution times directly rather
  than theorizing.
- Break down `WAREHOUSE_METERING_HISTORY` credits by which queries ran
  during each billed period, to see whether a small number of genuinely
  heavy queries justify the current size while the bulk of traffic
  doesn't.

## Fix
Right-size the warehouse based on measured execution time at different
sizes for the actual representative workload, not intuition -- start
smaller than assumed and scale up only if testing shows a real,
proportionate latency benefit. If the underlying problem is
concurrency/queuing rather than single-query speed, address it with a
multi-cluster warehouse (horizontal scaling) instead of a larger single
warehouse (vertical scaling), since Snowflake bills multi-cluster
scaling only when additional clusters actually spin up under load,
whereas a permanently large single warehouse bills its full size
continuously whenever it's running at all. Where workloads with
genuinely different resource needs share a warehouse, split them onto
separately-sized warehouses matched to each workload's actual profile
(see the workload-isolation skill for the queuing/contention angle of
this same split).

## Pitfalls
Downsizing based on a single quiet-period test can miss real peak-load
degradation -- test against the actual heaviest realistic window (e.g.
month-end batch, Monday-morning dashboard rush), not an arbitrary
sampled hour. Also, warehouse resizing takes effect only for queries
that start after the resize (running queries aren't affected), so
comparing "before/after" execution time incorrectly across a resize
boundary can produce misleading conclusions if some sampled queries
straddle the change.

## Verify
After resizing down, monitor `QUERY_HISTORY` execution times for the
same representative query set over a full realistic workload cycle
(including peak periods) and confirm latency remains acceptable, then
compare `WAREHOUSE_METERING_HISTORY` credit consumption before and after
to confirm the expected proportional cost reduction actually
materialized.
