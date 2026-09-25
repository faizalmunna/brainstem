---
name: cloudwatch-logs-cost-spike-no-retention
description: CloudWatch Logs costs spike unexpectedly because a Lambda or application log group logs verbosely and has no retention policy, retaining data indefinitely.
triggers: ["cloudwatch logs bill spike", "cloudwatch costs increasing", "lambda logging too much cloudwatch cost", "log group never expires", "cloudwatch ingestion cost high"]
permissions: ["READ"]
---

## Symptom
The AWS bill shows a disproportionate and growing CloudWatch Logs line
item -- either the ingestion cost (per-GB charge for data written) or the
storage cost (per-GB-month for retained data), or both -- often traced back
to one or a few log groups belonging to a Lambda function or service that
recently had its logging verbosity increased (e.g., debug-level logging
enabled and never turned back off) or that has simply been running for a
long time with default "Never Expire" retention.

## Likely causes
1. **Debug or verbose logging was enabled (for troubleshooting) and never
   reverted**, so every invocation now writes far more log data than
   before -- this shows up as an ingestion cost spike specifically dated
   to when the logging change was deployed, not a gradual drift.
2. **The log group's retention setting is "Never Expire" (the default for
   log groups created without explicit retention)**, so storage cost
   grows unbounded over the log group's entire lifetime even if daily
   ingestion volume is unremarkable -- this shows up as storage cost
   climbing steadily over months, distinct from an ingestion spike.
3. **A high-throughput Lambda function or service logs full request/response
   payloads (including large JSON bodies, base64 blobs, or verbose SDK
   client debug output)** on every invocation rather than sampling or
   truncating, so per-invocation log volume is inherently large
   regardless of overall invocation count.
4. **A misconfigured or looping process logs the same error repeatedly**
   (e.g., a retry loop with no backoff logging every failed attempt, or a
   health check hitting an error path every few seconds), multiplying
   ordinary log volume by an unintended repetition factor.
5. **CloudWatch Logs Insights queries or subscription filters/exports
   (e.g., streaming to a third-party log aggregator or S3) are
   themselves billed separately** and were added without accounting for
   their incremental cost on top of base ingestion/storage, so the
   "CloudWatch cost" spike is partly a different line item than raw log
   ingestion.

## Diagnose
- In Cost Explorer, filter by service (CloudWatch) and usage type to
  distinguish `DataProcessing-Bytes` (ingestion) from `TimedStorage-
  ByteHrs` (storage) from `DataScanned` (Insights queries) -- these have
  different causes and different fixes.
- Use `aws logs describe-log-groups` and sort by `storedBytes` to find
  the specific log groups responsible for the largest share, then check
  each one's `retentionInDays` -- `null`/absent means "Never Expire."
- For the top offending log group, check recent ingestion rate via the
  `IncomingBytes` CloudWatch metric on the `AWS/Logs` namespace,
  correlated against recent deploy timestamps for the owning
  service/function, to confirm whether it's a sudden spike (logging
  change) or a slow accumulation (missing retention on old data).
- Sample recent log entries directly (`aws logs tail` or the console) to
  check for unexpectedly verbose content -- full payload dumps, repeated
  identical error lines, or debug-level framework/SDK output that
  shouldn't be in production logs.
- Check for CloudWatch Logs subscription filters
  (`describe-subscription-filters`) forwarding this log group elsewhere,
  which incurs its own cost independent of base storage.

## Fix
Set an explicit, deliberate retention period (e.g., 14-30 days for most
application logs, longer only where compliance genuinely requires it) on
every log group via `PutRetentionPolicy`, rather than leaving new log
groups at the "Never Expire" default -- for Lambda, this means setting it
via infrastructure-as-code alongside the function definition so every new
function gets a retention policy automatically instead of relying on
someone remembering to set it manually per log group. Reduce logging
verbosity in code: gate debug-level logs behind an environment-controlled
log level that defaults to `INFO`/`WARN` in production, truncate or
summarize large payloads instead of logging them whole, and fix any
retry/error loop that logs identically on every iteration (log once with
a count, or use exponential backoff that also naturally reduces log
frequency). For log groups that must be retained long-term for
compliance, use a lifecycle transition to cheaper storage (export to S3
with an S3 lifecycle policy to Glacier) instead of paying CloudWatch's
storage rate indefinitely.

## Pitfalls
Setting retention to something very short (e.g., 1 day) across the board
to minimize cost can remove logs needed to investigate an incident that
isn't noticed until after that window passes -- pick a retention period
based on realistic incident-investigation and audit needs, not purely
cost minimization. Also, reducing log verbosity too aggressively (turning
off request-level logging entirely) can remove the very observability
needed to diagnose the next production issue -- the fix is removing
*redundant/oversized* logging, not logging depth generally; pair with
structured, leveled logging rather than a blanket reduction.

## Verify
After setting retention policies, confirm via `aws logs describe-log-
groups` that all production log groups show a finite `retentionInDays`
rather than none. After reducing verbosity, compare the `IncomingBytes`
metric for the affected log group over a matched time window
(same traffic pattern, days apart) before and after the change, and
confirm the next month's Cost Explorer CloudWatch Logs line item trends
down toward the expected baseline.
