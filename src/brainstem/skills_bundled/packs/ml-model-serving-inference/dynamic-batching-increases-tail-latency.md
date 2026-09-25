---
name: dynamic-batching-increases-tail-latency
description: Enabling dynamic request batching to improve model serving throughput unexpectedly worsens tail latency for individual requests that arrive just after a batch window closes.
triggers: ["dynamic batching hurt latency", "inference tail latency increased after batching", "batch window causing request delay", "model server p99 latency worse with batching"]
permissions: ["READ"]
---

## Symptom

After enabling dynamic batching (grouping multiple incoming inference
requests together to process on the GPU more efficiently) to improve
overall throughput, tail latency (p95/p99) for individual requests gets
noticeably worse, even though average throughput and average latency
both improved.

## Likely causes

- **A request that arrives just after a batch window has closed has to
  wait for the next full batch window before being processed**,
  adding the batch window duration as pure added latency for that
  specific unlucky request, and this effect is invisible in average
  latency but shows up clearly in tail percentiles.
- **The batch window/max-batch-size configuration is tuned for
  throughput without considering the latency SLA for individual
  requests** -- a longer batching window improves GPU utilization but
  directly trades off against worst-case per-request latency.
- **Traffic isn't uniformly distributed over time**, so during
  lower-traffic periods, a batch might wait the full window duration to
  accumulate even a small number of requests, adding latency precisely
  when it's least necessary for throughput reasons.
- **No separate handling exists for latency-sensitive requests versus
  throughput-optimizable ones**, treating all requests identically when
  some callers might have tighter real-time requirements than others.

## Diagnose

1. Measure the distribution of "time from request arrival to batch
   dispatch" specifically, separate from total end-to-end latency, to
   directly quantify how much of tail latency is attributable to
   batch-window waiting.
2. Correlate tail-latency-affected requests with their arrival time
   relative to batch window boundaries, confirming the "just missed the
   batch" pattern.
3. Check current batch window/max-batch-size configuration values against
   the actual latency SLA requirements for the service.
4. Check whether traffic volume varies enough over time that batch
   window wait time behaves differently at different times of day/load
   levels.

## Fix

Tune the batching configuration to balance throughput and tail latency
deliberately -- typically a shorter max batch window with a dynamic
trigger (dispatch immediately if a minimum batch size is reached, or
after a maximum wait time, whichever comes first) rather than always
waiting the full window. For genuinely latency-sensitive traffic,
consider a separate serving path or priority lane that bypasses batching
entirely (or uses a much shorter window) at some throughput cost,
reserving batching's full throughput benefit for less latency-sensitive
traffic. Make the maximum wait time an explicit, small value bounded by
the actual SLA requirement, not just tuned purely for maximum throughput.

## Pitfalls

Don't disable batching entirely in response to a tail-latency regression
without first trying to tune the window/trigger configuration -- a
well-tuned dynamic batching setup can often achieve most of the
throughput benefit with much less tail-latency cost than a naive
fixed-window implementation.

## Verify

After retuning, measure p95/p99 latency under realistic variable traffic
(including lower-volume periods where the "just missed the batch"
pattern is most likely) and confirm it's now within the required SLA,
while confirming throughput improvement from batching is still
meaningfully retained compared to no batching at all.
