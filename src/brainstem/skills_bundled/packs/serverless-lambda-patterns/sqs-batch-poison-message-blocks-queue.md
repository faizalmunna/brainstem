---
name: sqs-batch-poison-message-blocks-queue
description: One malformed message in an SQS-triggered function's batch causes the entire batch, including good messages, to be retried repeatedly.
triggers: ["sqs lambda one bad message retries whole batch", "poison message blocking queue", "sqs batch failure reprocessing good messages", "lambda sqs trigger stuck reprocessing"]
permissions: ["READ"]
---

## Symptom
An SQS-triggered function (Lambda, or an Azure Functions/Cloud Functions
equivalent consuming a queue) processes a batch of N messages, one of them
throws an exception partway through, and the entire batch -- including
messages that already succeeded -- gets marked as failed and redelivered.
The same handful of messages keep reappearing in logs every visibility
timeout period, throughput on the queue stalls, and eventually the
`ApproximateNumberOfMessagesNotVisible`/age-of-oldest-message metric climbs
even though most traffic is fine.

## Likely causes
1. **The function returns a single success/failure for the whole batch
   instead of reporting partial batch failures.** By default, an unhandled
   exception anywhere in the handler causes the platform to treat every
   message in that invocation's batch as failed and redeliver all of them,
   not just the one that errored.
2. **One message is structurally malformed or violates an assumption the
   handler makes** (missing field, wrong schema version, non-UTF8 payload)
   and every retry hits the same exception deterministically -- it's not a
   transient failure, so retrying it is pure waste and it will never
   succeed no matter how many times it's redelivered.
3. **No dead-letter queue (redrive policy) is configured**, or `maxReceiveCount`
   is set very high, so the poison message keeps cycling through the same
   queue indefinitely instead of being moved aside after a bounded number
   of attempts.
4. **Batch size is set too large for the failure blast radius the team is
   willing to accept** -- a batch of 10 means one bad message potentially
   delays/reprocesses 9 good ones every cycle, whereas a smaller batch (or
   partial-batch-failure reporting) shrinks the collateral damage.
5. **The handler's error handling swallows per-message context**, catching
   exceptions generically and re-throwing a single error for the batch,
   which erases the information needed to identify which specific message
   ID actually failed.

## Diagnose
- Check CloudWatch Logs (or equivalent) for the same message ID appearing
  across multiple invocation timestamps spaced roughly at the queue's
  visibility timeout interval -- that repetition pattern is the signature
  of a poison message, distinct from generic elevated error rate.
- Inspect the queue's `ApproximateAgeOfOldestMessage` metric -- a
  monotonically increasing value while throughput elsewhere looks normal
  indicates one or more messages stuck cycling at the head of processing.
- Pull the actual payload of the suspected message (via a manual
  `receive-message` call with a short visibility timeout, or from the DLQ
  if one exists) and run it through the handler's parsing/validation logic
  locally to reproduce the exception deterministically.
- Check the event source mapping configuration for
  `FunctionResponseTypes: ReportBatchItemFailures` (Lambda) or the
  equivalent partial-completion setting -- if absent, confirm that this is
  in fact causing whole-batch redelivery, not just the one message.
- Check the queue's redrive policy `maxReceiveCount` -- a high or unset
  value means the poison message hasn't reached the DLQ yet even after
  many visible retries.

## Fix
Report partial batch failures explicitly: process each message inside its
own try/catch, collect the message IDs that failed, and return only those
IDs as failed (Lambda's `batchItemFailures` response, or the equivalent for
other platforms) so the platform redelivers only the messages that
actually failed rather than the whole batch. Configure a dead-letter queue
with a bounded `maxReceiveCount` (typically 3-5) so a message that fails
deterministically is moved aside for inspection instead of looping forever.
Validate/parse the message schema defensively at the top of the handler and
route unparseable messages straight to the DLQ (or a separate
"quarantine" queue) rather than letting them throw deep in business logic
where the failure is harder to attribute. Size batch size deliberately: a
smaller batch limits blast radius per poison message at the cost of some
throughput efficiency, and is often the right tradeoff for queues with
heterogeneous, less-trusted producers.

## Pitfalls
Enabling partial batch failure reporting but forgetting to actually track
per-message success/failure state in the handler makes the situation worse:
if the code isn't restructured to report which specific messages failed,
a naive implementation can report the entire batch as failed even after
the feature is turned on, gaining nothing. Also, setting `maxReceiveCount`
very low (e.g., 1) on a queue with legitimately transient downstream
failures (a brief DB blip) sends messages to the DLQ that would have
succeeded on a normal retry -- the DLQ threshold should reflect genuine
non-transient failure, not just any first failure.

## Verify
Publish a batch containing one deliberately malformed message alongside
several valid ones, and confirm via logs/metrics that only the malformed
message's ID is retried (and eventually lands in the DLQ after
`maxReceiveCount` attempts) while the valid messages are processed exactly
once and do not reappear in subsequent invocations.
