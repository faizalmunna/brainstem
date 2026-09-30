---
name: duplicate-job-processing-at-least-once-delivery
description: A job's side effect happens more than once because the broker redelivered the message after an ack timeout or worker restart, not because of application-level retry logic.
triggers: ["job ran twice", "duplicate email sent from worker", "sqs redelivered message", "celery task executed multiple times", "visibility timeout too short"]
permissions: ["READ"]
---

## Symptom
The same job executes fully more than once -- a duplicate email, a duplicate charge, a duplicate row -- and investigation shows the *same* job id or message being redelivered by the broker itself (visible as a redelivered/receive-count flag), rather than the application enqueueing it twice or an explicit retry-after-failure path firing.

## Likely causes
1. **Visibility timeout / lock duration shorter than actual job runtime** (SQS `VisibilityTimeout`, BullMQ `lockDuration`, RabbitMQ consumer ack window) -- the broker assumes the worker died partway through and redelivers the message to another worker while the first is still legitimately finishing.
2. **Late-ack configuration combined with a worker crash or restart mid-job** (Celery `acks_late`, manual ack placed after task completion) -- the worker crashes (deploy, OOM, SIGKILL) after the side effect already ran but before the ack reached the broker, so the unacked message gets requeued and reprocessed.
3. **Broker delivery semantics that are at-least-once by design** (SQS standard queues, competing-consumer patterns, mirrored-queue failover in RabbitMQ redelivering unacked messages after a node failover) with no application-level defense assuming "the broker never duplicates."
4. **No idempotency check in the job handler itself**, so once broker-level duplicate delivery happens for any of the above reasons, nothing stops the side effect from running twice.

## Diagnose
- Check the broker's redelivery/receive-count metadata for the affected job id: SQS `ApproximateReceiveCount` > 1, RabbitMQ's `redelivered` flag, BullMQ `attemptsMade`, Sidekiq's job payload retry count -- confirm it's a broker-level redelivery, not two independent enqueue calls.
- Compare the configured visibility timeout/lock duration against the job's actual p99 execution time; a timeout set below p99 guarantees redelivery for the slowest jobs under normal operation.
- Correlate the duplicate execution's timestamps with worker restart/deploy/OOM-kill events in the same window in the process logs or orchestrator events.
- Check whether the job handler has any dedup/completion-marker check at all (grep for an "already processed" guard) -- its absence confirms there's no defense once redelivery occurs.

## Fix
Treat at-least-once delivery as the permanent contract of the queue, not a bug to eliminate -- it cannot be fully prevented, only made safe. Set the visibility timeout/lock duration comfortably above p99 job runtime, and for genuinely long jobs extend it via a heartbeat while the job is still running (SQS `ChangeMessageVisibility`, BullMQ lock renewal) rather than picking one large static value. Separately, make the handler idempotent at the point of the side effect: record a completion marker keyed on the job's *business* identity (order id, recipient+template, not the broker's message id) before or atomically with performing the side effect, and check that marker at the start of every execution attempt, including the first. On deploy/restart, prefer graceful shutdown (SIGTERM handling that lets in-flight jobs finish or cleanly requeue) over SIGKILL to shrink the crash-mid-job window, while still relying on idempotency as the real safety net since the window can never be fully closed.

## Pitfalls
- Extending the visibility timeout to a very large blanket value "to be safe" just delays detection of a genuinely dead worker's job -- pair a longer timeout with heartbeat-based extension, not one oversized static number.
- Keying the idempotency check on the broker's own message/delivery id doesn't help, since that id changes on every redelivery -- key it on the business operation the job represents.

## Verify
In staging, force redelivery deliberately (kill the worker mid-job, or temporarily set the visibility timeout below the job's runtime) and confirm the job body executes twice at the broker level but the side effect -- and any metric counting it -- only happens once, because the second execution hits the completion marker and no-ops.
