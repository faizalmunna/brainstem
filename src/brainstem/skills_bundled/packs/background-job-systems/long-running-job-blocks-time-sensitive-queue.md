---
name: long-running-job-blocks-time-sensitive-queue
description: Short, time-sensitive jobs like password-reset emails are delayed for minutes because they queue behind long-running jobs sharing the same workers.
triggers: ["password reset email delayed", "urgent job stuck behind bulk export", "notification job delayed by report generation", "no queue priority separation", "fast jobs waiting behind slow jobs"]
permissions: ["READ"]
---

## Symptom
Short, time-sensitive jobs (a password-reset email, a real-time notification) are delayed by minutes even though workers are otherwise healthy and the overall queue doesn't look backlogged on average, traced to those jobs sitting behind one or more long-running jobs (bulk exports, report generation) occupying the same worker pool.

## Likely causes
1. **All job types share a single queue and worker pool with no separation by priority or expected duration**, so near-FIFO ordering means a long job dequeued first occupies its worker slot for its entire duration regardless of what more urgent work arrives after it.
2. **Worker concurrency is correctly sized for aggregate throughput, but a small number of long jobs can occupy a large fraction of available slots simultaneously** (e.g. 2 of 4 workers tied up in hour-long exports), leaving too few slots for bursty short jobs to be picked up quickly even though the queue looks healthy in aggregate.
3. **A priority mechanism exists at the queue level but is misconfigured or unused** (BullMQ job priority, Sidekiq queue weights), so every job is effectively enqueued at the same priority regardless of actual urgency.
4. **Long jobs aren't broken into checkpointed chunks**, so there's no natural point where a scheduler could interleave a higher-priority job -- once dequeued, a long job monopolizes its slot until full completion.

## Diagnose
- Check the queue/routing configuration directly to confirm whether time-sensitive job types actually share a queue and worker pool with known long-running types, rather than assuming based on naming conventions alone.
- Measure the wait-time distribution specifically for the time-sensitive job type (not aggregate queue latency), and correlate spikes with periods when long-running jobs were also executing.
- Check worker slot occupancy at the moment of a reported delay incident -- how many of the total concurrency slots were held by long-running jobs at that time.

## Fix
Route job types to separate queues based on expected duration/urgency (a `fast`/`default`/`bulk` split), each consumed by its own dedicated worker pool sized independently, so a burst of long jobs in one queue structurally cannot starve workers dedicated to another. Where the system supports genuine priority within a shared pool, configure it explicitly and verify callers actually populate the intended priority value -- an unused priority field doesn't help. Decompose long jobs that can be chunked into a chain of smaller sub-tasks (e.g. paginating a bulk export into per-page jobs) so worker slots free up between chunks instead of being held for the whole operation, which incidentally also makes the job resumable after a partial failure. Reserve a minimum number of worker slots exclusively for the time-sensitive queue rather than relying on a fully shared pool with priority ordering alone, so a burst of long jobs can never claim all capacity.

## Pitfalls
Splitting into separate queues without also splitting the worker pools doesn't help if the same processes still consume from both queues in a way that lets a long job block that worker regardless of which queue it came from -- the separation has to reach the worker/concurrency layer, not just the queue layer. Over-fragmenting into many narrow priority queues, each with tiny dedicated capacity, can leave individual queues under-provisioned for their own bursts -- balance separation against creating new, smaller backlog problems per queue.

## Verify
Enqueue a batch of long-running jobs alongside a steady trickle of time-sensitive jobs in staging and measure the time-sensitive job's p95 wait time before and after the fix -- confirm it stays within its target SLA regardless of the concurrent long-job batch.
