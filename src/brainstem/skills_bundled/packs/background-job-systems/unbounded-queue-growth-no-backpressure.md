---
name: unbounded-queue-growth-no-backpressure
description: Queue depth climbs steadily even outside traffic spikes because producers keep enqueueing faster than consumers can drain with no mechanism to slow them down.
triggers: ["queue never stops growing", "redis running out of memory from queue", "rabbitmq disk alarm from queue growth", "producers outpacing consumers", "no backpressure on job queue"]
permissions: ["READ"]
---

## Symptom
The queue's message count grows steadily over an extended period and never drains back down even during quiet traffic windows, eventually threatening broker memory/disk exhaustion (Redis OOM, a RabbitMQ disk alarm, ballooning cost/latency on a technically-unbounded queue like SQS) -- distinct from a temporary backlog that recovers once a burst subsides.

## Likely causes
1. **Producers enqueue at a sustained rate that structurally exceeds total consumer throughput**, not just during bursts -- often introduced by a new feature enqueueing jobs, or a batch import added without checking it against consumer capacity.
2. **No mechanism exists for producers to sense queue pressure and slow down** -- enqueue calls always succeed immediately regardless of current depth, so no signal about backlog ever reaches the producer side.
3. **Consumer throughput silently degraded at the same time producer rate stayed constant** (a downstream dependency got slower, a bug increased per-job processing time), turning a previously-balanced system structurally unbalanced without one single obvious trigger event.
4. **Retried/requeued jobs are counted alongside genuinely new arrivals**, inflating the effective arrival rate beyond what producer-side enqueue logs alone would suggest, masking the true imbalance.

## Diagnose
- Plot queue depth over a period long enough to distinguish sustained growth from burst-and-recover (days, not minutes) -- depth still climbing during quiet traffic periods indicates a structural imbalance.
- Compute enqueue rate and dequeue/completion rate as two separate time series over the same window; enqueue consistently exceeding dequeue even outside peak hours confirms the imbalance, distinct from a pure capacity question solvable by adding workers alone.
- Check whether producers have any conditional logic reacting to queue depth or a rejection/backpressure signal at all, versus enqueueing unconditionally regardless of backlog.
- Break down current depth by original-enqueue versus requeued-after-retry to see whether retries are inflating the apparent arrival rate.

## Fix
Add an explicit backpressure mechanism on the producer side: reject or defer new enqueues once depth crosses a threshold (a retryable error/429 back to whatever triggered the enqueue, or routing to a degraded/slower path) instead of accepting unlimited work unconditionally. Where producers can't reasonably slow down because they're driven directly by user actions, apply load shedding or prioritization at the edge instead -- drop or sample lower-priority job types first once depth crosses a threshold, rather than treating all enqueued work as equally mandatory. Set a hard maximum queue length at the broker level where supported (RabbitMQ `x-max-length` with an overflow policy, a bounded channel) as a last-resort circuit breaker that produces a visible, immediate error instead of unbounded growth ending in an uncontrolled broker failure. Separately, fix the actual throughput imbalance identified in diagnosis -- scale consumers to match sustained producer rate, or fix the downstream slowdown -- since backpressure prevents catastrophic failure but doesn't resolve a genuine, sustained capacity deficit on its own.

## Pitfalls
Backpressure that drops or fails all excess work equally treats a critical job the same as a low-priority one -- combine backpressure with priority awareness so any necessary shedding drops the least important work first. A hard max-queue-length with no monitoring on how often it's actually triggered just converts silent unbounded growth into silent, unbounded producer-side failures -- alert on the rejection/shedding rate the same way you'd alert on queue depth itself.

## Verify
Run a sustained load test where producer rate is deliberately held above consumer throughput for an extended period, not just a short burst, and confirm queue depth plateaus at the configured maximum (or the backpressure signal starts rejecting/shedding) rather than growing without bound, with the rejection/shedding rate visible in metrics.
