---
name: dynamodb-streams-retention-expiry-data-loss
description: A DynamoDB Streams consumer falls permanently behind and silently loses change events once the 24-hour stream retention window expires before it catches up.
triggers: ["dynamodb streams data loss", "TrimmedDataAccessException", "dynamodb stream consumer falling behind", "dynamodb streams 24 hour retention", "lambda dynamodb stream iterator age growing"]
permissions: ["READ"]
---

## Symptom
Downstream systems fed by a DynamoDB Streams consumer (a Lambda event
source mapping, or a Kinesis Client Library-based consumer) are missing
records -- not erroring loudly, just quietly out of sync with the table.
Investigating turns up either a `TrimmedDataAccessException` (the shard
iterator points at a sequence number that's already aged out) or, more
insidiously, no error at all because the consumer's checkpoint just moved
forward past a gap. The root timeline: the consumer fell behind
processing (Lambda errors and retries, a downstream dependency outage, an
undersized consumer), and DynamoDB Streams only retains change records
for a fixed **24-hour window** -- once records age out of that window,
they are gone permanently; there is no replay, no S3 archive fallback
built into the stream itself.

## Likely causes
1. **The stream consumer (commonly a Lambda function via event source
   mapping) is erroring on a subset of records and retrying indefinitely**
   -- by default, Lambda's DynamoDB event source mapping retries a failed
   batch and does not advance the iterator past it, so one persistently
   poison record can block the entire shard's forward progress while new
   records keep arriving and the 24-hour clock keeps running on the
   oldest unprocessed ones.
2. **The consumer's processing throughput is simply lower than the
   table's write throughput** -- e.g. each record triggers a slow
   downstream call (another API, a cross-region write) and average
   processing time per batch exceeds the rate new records are produced,
   so the backlog grows monotonically rather than draining.
3. **A downstream dependency the consumer writes to (another database, an
   external API, an SQS queue at its own limit) has an extended outage**,
   during which the consumer either fails and retries or blocks, and if
   the outage lasts close to or beyond 24 hours, records produced near
   the start of the outage age out before they can ever be delivered.
4. **The event source mapping or KCL application was paused or disabled**
   (deployment mistake, IAM permission change breaking it silently,
   manual disable during an unrelated incident) and nobody noticed within
   the 24-hour window because there was no alerting on stream **iterator
   age** specifically.

## Diagnose
- Check the Lambda event source mapping's `IteratorAge` CloudWatch metric
  (`GetRecords.IteratorAgeMilliseconds` for Streams-based sources) --
  this directly measures how far behind the consumer is from the stream's
  head, in time; a value approaching 24 hours is an active, urgent
  data-loss-imminent condition, not just a performance concern.
- Check the Lambda function's own error rate and the event source
  mapping's `bisect-batch-on-function-error` / retry configuration -- a
  high, sustained error rate on a specific record shape is the direct
  signature of a poison-pill record blocking shard progress.
- Look for `TrimmedDataAccessException` in consumer logs, which confirms
  records have already aged out (loss has already happened, not just
  about to).
- Review whether the event source mapping is even enabled/active (`aws
  dynamodbstreams describe-stream` and check the Lambda event source
  mapping's `State`) -- a disabled mapping produces no errors at all,
  just silent non-processing.
- Check downstream dependency health/incident history for the relevant
  window if IteratorAge shows a sudden, sustained climb rather than
  gradual drift, since that points at an external outage rather than a
  capacity mismatch.

## Fix
Alert on `IteratorAgeMilliseconds` well before it approaches the 24-hour
ceiling -- a common threshold is alerting at a few hours, giving on-call
time to intervene before any loss occurs, not just when loss is imminent
or has already happened. For poison-pill records, configure the event
source mapping with `BisectBatchOnFunctionError` and a `MaximumRetryAttempts`
cap combined with a **destination for failed batches** (an SQS dead-letter
queue or another Lambda), so one bad record is isolated and reported
instead of blocking the whole shard indefinitely. For sustained
throughput mismatches, increase parallelization (`ParallelizationFactor`
on the event source mapping allows multiple concurrent invocations per
shard) or reduce per-record processing latency. As a structural
safeguard for any workload where losing change events is unacceptable,
don't rely on Streams' 24-hour window as the only durable record --
either fan changes out to a longer-retention store immediately (Streams
-> Kinesis Data Streams with extended/long-term retention, or Streams ->
Firehose -> S3) as close to real-time as possible, so a slow consumer
reads from a durable buffer with room to catch up rather than from
Streams' own short window directly.

## Pitfalls
Simply catching and swallowing errors in the consumer to "stop it from
blocking" prevents the shard-stall symptom but silently drops the
records that errored -- that's data loss with better vitals, not a fix;
failed records need to go somewhere durable (a DLQ), not `/dev/null`.
Also, increasing Lambda concurrency/parallelization factor helps
throughput-mismatch cases but does nothing for the poison-pill case,
since more parallel workers just means more workers retrying the same
bad batch -- the two causes need different fixes and it's easy to apply
only one.

## Verify
After deploying a fix, confirm `IteratorAgeMilliseconds` trends back down
toward a low, stable baseline (seconds to low minutes) rather than
climbing, and confirm any DLQ/failure-destination configured for the
event source mapping is actually receiving isolated failed records
(proving poison records are contained, not blocking) during a controlled
test with a deliberately malformed record.
