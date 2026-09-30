---
name: queue-backlog-insufficient-worker-concurrency
description: The job queue's depth grows continuously during normal operation and jobs execute long after being enqueued, with no autoscaling responding to the backlog.
triggers: ["queue keeps growing", "jobs taking forever to process", "worker backlog never drains", "sidekiq queue latency high", "celery queue length increasing"]
permissions: ["READ"]
---

## Symptom
Queue depth (SQS `ApproximateNumberOfMessagesVisible`, RabbitMQ `messages_ready`, Redis list length / BullMQ waiting count, Sidekiq queue latency) trends upward over hours or days rather than oscillating around a stable baseline, and jobs sit waiting far longer than their expected turnaround -- distinct from a short burst that drains on its own.

## Likely causes
1. **Worker/concurrency count sized for average load, not peak or sustained arrival rate**, so any period where arrival exceeds a fixed processing rate adds permanently to the backlog instead of just delaying a burst.
2. **Concurrency setting mismatched to the job's actual bottleneck** -- I/O-bound jobs (waiting on network calls) run with a low thread/process concurrency suited to CPU-bound work, wasting available capacity, while genuinely CPU-bound jobs are over-concurrent for the number of cores available.
3. **Autoscaling wired to the wrong signal** -- scaling policy watches CPU or memory utilization, which stays low for I/O-bound job workers even while the queue backs up, so no scale-out ever triggers despite a real backlog.
4. **A downstream dependency got slower**, silently increasing per-job duration without any config change, which reduces effective throughput even though concurrency numbers on paper haven't changed.

## Diagnose
- Chart queue depth, enqueue rate, and completion rate together over the same window; sustained growth where completion rate stays flat below enqueue rate confirms a structural (not bursty) imbalance.
- Apply Little's Law as a sanity check: required concurrency ≈ arrival_rate × average_job_duration; compare against the currently configured concurrency.
- Check the autoscaling policy's actual scaling metric (CPU/memory vs. queue-depth or queue-latency based, e.g. KEDA `ScaledObject` on queue length) -- a CPU-based policy on I/O-bound workers explains "backlog with low CPU."
- Check the trend of per-job execution duration (p50/p95) over the same period for a silent regression from a downstream call.

## Fix
Size concurrency to the actual bottleneck: for I/O-bound jobs, increase concurrent workers/threads/greenlets well beyond the core count (the extra concurrency is spent waiting on I/O, not competing for CPU); for CPU-bound jobs, scale processes/nodes up to available cores instead. Point autoscaling at a queue-depth or queue-latency metric rather than CPU/memory, since job workers can be maxed out on backlog while sitting at low CPU utilization the whole time. Separate long-running outlier job types into their own queue and worker pool (see the long-running-job/priority-queue pattern) so a slowdown in one job type doesn't distort the throughput picture for the rest. Add a backlog/latency alert independent of autoscaling, so a human gets paged if the backlog grows faster than autoscaling's ceiling can absorb.

## Pitfalls
Cranking concurrency up without checking downstream capacity (a database connection pool, a third-party API's rate limit) just relocates the bottleneck into a new failure mode -- connection pool exhaustion or 429 responses -- instead of increasing real throughput. Autoscaling purely on raw queue depth, without accounting for job duration variance, over-reacts to a burst of many fast jobs and under-reacts to a smaller number of slow ones -- scale on a derived "estimated drain time" (depth divided by current throughput) where the platform supports a custom metric.

## Verify
Run a load test that pushes enqueue rate above steady-state for a sustained period, then stop, and confirm queue depth peaks and fully drains back to near-zero within the target SLA window, with metrics showing worker count increased in response to the queue-depth signal specifically (not merely to a coincidental CPU bump).
