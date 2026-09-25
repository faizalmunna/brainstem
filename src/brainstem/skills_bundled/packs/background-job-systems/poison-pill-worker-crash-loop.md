---
name: poison-pill-worker-crash-loop
description: A worker process repeatedly crashes or restarts on the same message because the job payload itself triggers an unhandled crash before it can be nacked or failed cleanly.
triggers: ["worker crash loop", "same job crashing every worker", "poison message stuck in queue", "kubernetes pod crashlooping on queue consumer", "worker keeps restarting on same task"]
permissions: ["READ"]
---

## Symptom
A worker fleet crash-loops or restarts repeatedly, and log inspection shows the same job id or message payload being dequeued immediately before every crash -- the queue never progresses past that one message, and each restart just re-fetches it and crashes again.

## Likely causes
1. **The payload itself crashes the process** before the job's own exception handling can run -- an oversized payload causing an OOM kill, a deserialization error raised outside any try/except, or a native-dependency crash (segfault) -- so the worker dies without ever nacking or failing the job cleanly, and the broker requeues it to the next worker.
2. **Retry-on-any-exception with no max-retry ceiling**, on a deterministic (not transient) failure -- a malformed payload or a permanently missing dependency that will never succeed -- so it retries indefinitely, looping rather than exhausting a retry budget.
3. **Retry-count tracking lives only in worker memory** rather than persisted on the message/job record, so each crash-and-restart resets the count to zero and no single worker's own counter ever reaches the configured max, even though the *message* has effectively been attempted many times across different workers.
4. **The orchestrator's restart policy has no backoff cap** (an external supervisor or a restart loop that restarts the process instantly rather than with exponential backoff), so the crash loop runs many cycles per minute, outpacing any max-delivery-count check.

## Diagnose
- Correlate crash timestamps across multiple worker instances/restarts with the broker's message id or job id dequeued immediately prior, to confirm it's genuinely the same message looping, not several independent unrelated crashes.
- Check where the retry counter actually lives: broker/message-persisted (SQS `ApproximateReceiveCount`, a retry-count field on the job record, BullMQ `attemptsMade`) versus purely in-process memory that a crash resets.
- Try deserializing/inspecting the specific payload manually, outside the worker, to confirm whether it's malformed, oversized, or otherwise structurally bad rather than just triggering an ordinary application exception.
- Check the orchestrator's restart/backoff configuration for the worker process or pod to see whether it allows rapid, uncapped restart cycles.

## Fix
Ensure retry-count tracking is broker- or record-persisted, not in-worker-memory, so the count survives crashes and is enforced across every worker instance that ever touches the message. Configure a hard max-delivery-count at the queue level (SQS redrive policy `maxReceiveCount`, a RabbitMQ dead-letter exchange after N deaths, BullMQ/Sidekiq max attempts) that routes the message to a dead-letter queue once exceeded, independent of any application-level retry logic that a hard crash can bypass entirely. Add defensive validation at the very start of message handling -- bound payload size, wrap deserialization in a try/except that fails the job cleanly with a normal exception instead of letting it crash the process. Cap the orchestrator's restart rate (Kubernetes' default crash-loop backoff, or equivalent in a custom supervisor) so the loop can't cycle faster than the max-delivery-count mechanism can catch up.

## Pitfalls
Raising the retry ceiling "to be safe" just makes a true poison pill take longer to reach the dead-letter queue while still consuming worker capacity every cycle -- the fix is a hard ceiling plus a DLQ, not a bigger ceiling. Catching payload/deserialization errors too broadly can also swallow legitimate transient errors that should still retry -- distinguish "this payload can never be processed" (dead-letter immediately) from "this specific attempt failed" (retry with backoff).

## Verify
Manually enqueue a deliberately malformed or oversized payload in staging and confirm the worker logs a clean failure with no process crash, the delivery count increments and is visible on the message/job record across a simulated worker restart, and it lands in the dead-letter queue after the configured maximum instead of looping indefinitely.
