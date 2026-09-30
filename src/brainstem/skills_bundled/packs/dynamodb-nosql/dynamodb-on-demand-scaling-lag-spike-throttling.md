---
name: dynamodb-on-demand-scaling-lag-spike-throttling
description: A DynamoDB table on on-demand capacity mode still throttles requests for several minutes during a sudden traffic spike before internal scaling catches up.
triggers: ["dynamodb on-demand still throttling", "dynamodb sudden traffic spike throttled errors", "dynamodb on demand mode not scaling fast enough", "dynamodb throttling during launch traffic spike", "on-demand dynamodb previous peak doubling"]
permissions: ["READ"]
---

## Symptom
A table configured with on-demand capacity mode -- chosen specifically to
avoid manual capacity planning -- still returns throttling errors (or, on
the SDK side, elevated retry counts and latency) during a sudden traffic
ramp, such as a marketing push, a product launch, or a batch job kicking
off simultaneously across many workers. The team's assumption was that
on-demand mode removes throttling risk entirely; the reality is it
removes *manual* capacity planning, not the physical scaling lag of
provisioning new partition capacity to match load that increases faster
than DynamoDB's internal scaling can react.

## Likely causes
1. **Traffic more than doubled the previous peak within a very short
   window**, and on-demand tables scale their internal capacity based on
   the table's recent traffic patterns -- a jump well beyond roughly 2x
   the prior 30-minute peak, especially with little warning, can outpace
   how fast DynamoDB provisions additional partition-level capacity behind
   the scenes.
2. **The spike is concentrated on one or a few partition keys rather than
   spread evenly**, compounding this with the hot-partition problem: even
   a table-level capacity increase doesn't help if the actual bottleneck
   is per-partition throughput on a small number of hot keys, which
   on-demand scaling doesn't eliminate any more than provisioned mode
   does.
3. **The table (or a GSI on it) was recently created or had very low
   baseline traffic**, so there's little to no recent traffic history for
   DynamoDB's scaling logic to have already provisioned ahead of -- a
   cold or low-traffic table facing its first real spike has less
   pre-warmed capacity than one with a steady, gradually climbing traffic
   history.
4. **A batch process or scheduled job (a cron-triggered backfill, a
   nightly report, a cache-warming job) issues a burst of near-simultaneous
   requests** that looks nothing like organic gradual traffic growth,
   which is a harder pattern for automatic scaling (in either capacity
   mode) to anticipate than gradually ramping load.

## Diagnose
- Check CloudWatch `ThrottledRequests` and `ConsumedReadCapacityUnits`/
  `ConsumedWriteCapacityUnits` around the spike's start time -- confirm
  throttling is concentrated in the first minutes of the spike and
  subsides as it continues, which is the signature of a scaling-lag
  window rather than a sustained undercapacity problem.
- Compare the spike's peak traffic against the table's traffic over the
  preceding 30 minutes and, more broadly, its recent days -- quantify
  whether the jump exceeds roughly double the recent peak, which is the
  documented threshold where on-demand scaling is most likely to lag.
- Check whether throttling is table-wide or concentrated on specific keys
  using Contributor Insights, to rule in or out a concurrent hot-partition
  problem riding along with the aggregate spike.
- Check the table's traffic history for how recently it was created or
  whether it had a long low-traffic baseline before the spike, which
  affects how much pre-provisioned headroom existed going in.
- If the spike source is a known batch job, check its invocation pattern
  (all workers starting simultaneously vs staggered) -- a thundering-herd
  start pattern is directly actionable independent of DynamoDB capacity
  mode.

## Fix
For genuinely unpredictable spikes, pre-warm the table ahead of a known
event (a launch, a marketing campaign) by temporarily switching to
provisioned mode with capacity set above the expected peak, or by driving
synthetic traffic at a level close to the expected peak for a period
beforehand so on-demand's internal scaling has already provisioned ahead
of the real event -- DynamoDB explicitly supports and recommends this
"pre-warming via anticipated traffic" approach for known large spikes.
For recurring/predictable spikes (a daily or weekly pattern), provisioned
capacity with Application Auto Scaling targeting a lower utilization
threshold (scaling up earlier, before hitting the ceiling) can react
ahead of the spike rather than after it, since auto scaling policies can
be tuned more aggressively than on-demand's internal heuristics for a
known pattern. For batch/backfill-driven spikes, throttle the batch job
client-side (rate limiting, staggered worker start, exponential backoff
on retries) so it ramps its own request rate gradually instead of
presenting DynamoDB with an instantaneous step-function of demand.
Implement retry with exponential backoff and jitter in all clients
regardless -- transient throttling during a scaling window is expected
behavior, not a bug, and well-behaved clients should absorb it gracefully
rather than fail user-facing requests outright.

## Pitfalls
Treating "switch to on-demand" as a permanent substitute for capacity
planning for a business with known, large, predictable traffic events is
a common mistake -- on-demand is best for unpredictable or highly variable
workloads, but a known launch is exactly the case where provisioned mode
with pre-scaled capacity (or a temporary on-demand-to-provisioned switch)
gives more control than hoping on-demand's reactive scaling keeps up.
Also, retrying aggressively without backoff during a throttling window
makes the scaling lag worse, not better -- a retry storm adds to the very
demand spike that caused the throttling in the first place.

## Verify
Re-run (or wait for) a comparable traffic spike after pre-warming or
switching strategy, and confirm `ThrottledRequests` stays at or near zero
through the ramp-up period specifically (not just at steady-state peak),
using CloudWatch metrics scoped to the same time-of-spike window as the
original incident for a fair comparison.
