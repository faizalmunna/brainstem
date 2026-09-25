---
name: cosmos-db-ru-throttling-traffic-spike
description: A Cosmos DB container starts returning 429 request-rate-too-large responses during a traffic spike because provisioned or autoscale throughput was undersized.
triggers: ["cosmos db 429 too many requests", "cosmos db throttling during traffic spike", "request rate too large cosmos", "cosmos autoscale not scaling fast enough"]
permissions: ["READ"]
---

## Symptom
During a traffic spike (a marketing push, a batch job, a retry storm from
an upstream service), a Cosmos DB container that normally serves requests
without issue starts returning HTTP 429 (`Request rate is large`)
responses. The SDK's built-in retry logic masks some of it as added
latency, but past a certain point requests fail outright or latency
becomes unacceptable, even though the container "usually has enough
throughput."

## Likely causes
1. **Manually provisioned RU/s was sized for average load, not peak**, so
   a traffic spike simply exceeds the fixed RU ceiling and every request
   past that ceiling gets throttled until the next per-second window,
   regardless of autoscale being an option that wasn't chosen.
2. **Autoscale is enabled but its max RU/s ceiling (typically 10x the
   scaled-to-minimum) is still lower than the spike's actual demand** --
   autoscale protects against under-provisioning within its configured
   range, not unbounded, so a spike large enough can throttle even an
   autoscale-enabled container if the max wasn't set high enough for the
   realistic worst case.
3. **A hot partition is absorbing a disproportionate share of the spike's
   traffic** because the partition key has low cardinality or the spike's
   traffic pattern skews toward a small number of key values (e.g., one
   tenant ID during a single customer's burst), so the container's
   *aggregate* RU/s looks sufficient while that one physical partition's
   share of it is exhausted -- Cosmos DB throttles per-partition, not just
   in aggregate.
4. **Expensive cross-partition queries or a missing/suboptimal index**
   consume far more RU per request than expected under load, so the same
   request volume as before now costs more RU per request and crosses the
   throughput ceiling sooner than a naive requests-per-second estimate
   would predict.
5. **The retry storm is self-inflicted** -- an upstream client's own
   retry-on-429 logic, especially without exponential backoff and jitter,
   amplifies the spike by resubmitting failed requests immediately,
   turning a moderate spike into a sustained overload that never lets the
   container recover within a rate window.

## Diagnose
- In Azure Monitor metrics for the Cosmos DB account, check **Total
  Request Units** and **429 responses (Throttled Requests)** on the
  specific database/container, correlated in time with the traffic spike,
  to confirm throttling coincides with the spike rather than a separate
  issue.
- Check **Normalized RU Consumption** per physical partition (available in
  Azure Monitor metrics with partition key range dimension, or via the
  Cosmos DB portal's "Insights" tab) -- a partition sitting near 100% while
  others are low confirms a hot-partition cause rather than aggregate
  undersizing.
- Review the RU charge per request type using the SDK's response headers
  (`x-ms-request-charge`) or Cosmos DB diagnostic logs for the specific
  operations active during the spike, to see if a particular query pattern
  is unexpectedly expensive.
- Check the container's indexing policy for whether it excludes paths
  used by the spike's query patterns, or whether a query is doing a
  cross-partition scan (`FeedResponse` diagnostics show
  `documentServiceRequestCount` or query metrics with high RU relative to
  result size).
- If autoscale is enabled, check the configured max RU/s against the
  observed peak RU demand during the spike in Azure Monitor -- if peak
  demand regularly approaches or exceeds the max, the ceiling itself is
  the constraint, not autoscale's responsiveness.

## Fix
Match the throughput model to the actual traffic shape: enable autoscale
for workloads with variable or unpredictable spikes and set its max RU/s
based on a realistic worst-case peak (not just current average x 10), or
increase provisioned RU/s ahead of known spike events (a scheduled
campaign) if the timing is predictable and autoscale's automatic ramp
isn't fast enough for the specific spike shape. Fix hot-partition
exposure at the data-model level by choosing a partition key with high
cardinality and even access distribution for the workload's actual query
and write patterns, not just for storage distribution. Reduce per-request
RU cost by tightening the indexing policy to only the paths actually
queried and rewriting cross-partition queries to include the partition key
where possible. Ensure client SDKs use the built-in retry-with-backoff
behavior (`RetryOptions` in the .NET/Java/JS SDKs) rather than custom
immediate-retry logic, so transient 429s don't compound into a sustained
overload.

## Pitfalls
Raising provisioned RU/s (or autoscale max) as the only fix without
addressing a hot partition just delays the same failure at a higher cost
-- the skewed partition will still saturate before the container's
aggregate ceiling is reached, so money is spent on headroom the hot
partition can't use. Also, disabling client-side retry entirely to "stop
masking the problem" removes a legitimate resilience mechanism for
genuinely transient throttling; the fix is correct retry configuration
(bounded, backed off, jittered), not no retry.

## Verify
Reproduce a representative load pattern (a load test matching the spike's
request volume and key distribution) against the corrected configuration
and confirm 429 rates in Azure Monitor stay near zero. Check Normalized RU
Consumption per partition during the same test to confirm no single
partition approaches 100% while others sit idle. Confirm the container's
actual RU charge per operation, measured via response headers during the
test, matches expectations after indexing/query changes.
