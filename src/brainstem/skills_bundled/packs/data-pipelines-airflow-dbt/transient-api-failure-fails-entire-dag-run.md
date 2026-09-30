---
name: transient-api-failure-fails-entire-dag-run
description: A task calling an external API has no retry or backoff configured, so one transient failure fails the whole DAG run and requires manual re-triggering.
triggers: ["airflow task fails on transient api error", "dag failed due to timeout needs manual rerun", "no retry on external api call airflow", "flaky third party api breaks pipeline", "airflow task fails intermittently on network error"]
permissions: ["READ"]
---

## Symptom
A DAG run fails, and investigation shows the actual cause was a brief,
transient issue calling an external system -- a momentary 503, a
connection timeout, a rate-limit response -- that would very likely have
succeeded on a retry seconds later. Instead, the task failed outright,
marked the DAG run as failed, and someone had to notice and manually
click "clear" or re-trigger to get the pipeline to complete, often hours
after the fact.

## Likely causes
1. **The task/operator has no `retries` configured** (or `retries=0`,
   Airflow's default for an operator that doesn't set it explicitly), so
   Airflow makes exactly one attempt and marks the task failed on any
   exception, transient or not.
2. **Retries are configured but with no `retry_delay` or backoff,**
   causing immediate retries that hit the same transient condition again
   (a rate limiter that hasn't reset, a service still mid-restart) and
   burn through the retry budget without ever waiting long enough for the
   underlying issue to clear.
3. **The task's own code catches exceptions too broadly or too narrowly
   for what should be retryable** -- either it catches and swallows all
   errors (masking real failures as false successes) or it lets Airflow's
   task-level retry handle everything indiscriminately, including errors
   that will never succeed on retry (a 400 Bad Request, a malformed
   payload), wasting retry attempts and delaying the failure signal for
   genuinely broken calls.
4. **No circuit-breaking or rate-limit awareness**, so a task's retries
   (or many parallel task instances all retrying at once) hammer an
   already-struggling external service harder, worsening the very
   condition causing the failures.

## Diagnose
- Check the task/operator definition (or the DAG's `default_args`) for
  `retries` and `retry_delay` -- confirm whether they're set at all, and
  if so, whether the delay is long enough to plausibly outlast the kind
  of transient failure actually observed in the logs.
- Read the actual exception/stack trace from the failed task run and
  classify it: is it a genuinely transient condition (timeout, 5xx,
  connection reset, rate-limit 429) or a deterministic one (4xx client
  error, auth failure, malformed request) that retrying blindly wouldn't
  fix?
- Check whether `retry_exponential_backoff` is enabled, or whether
  retries (if configured) are firing back-to-back at a fixed short
  interval -- look at the task instance's try-number timestamps in the
  Airflow UI to see actual retry spacing.
- Check if multiple tasks/DAGs call the same external API and whether a
  spike in calls (from a backfill, a retry storm, or unrelated DAGs)
  correlates with the timing of the failures, suggesting the caller is
  contributing to the transient condition rather than being an innocent
  victim of it.

## Fix
Configure retries deliberately rather than leaving the default: set
`retries` to a small number appropriate to the operation (2-4 is typical
for network calls) with `retry_delay` and `retry_exponential_backoff=True`
so each attempt waits longer than the last, giving a transient condition
real room to clear rather than hammering it immediately. Inside the
task's own code, distinguish retryable from non-retryable errors
explicitly -- catch known-transient exception types (timeouts,
connection errors, specific retryable HTTP status codes) and re-raise
them so Airflow's retry mechanism engages, while letting deterministic
errors (4xx, validation failures) fail fast without burning retry
attempts, since retrying those only delays an accurate failure signal.
For calls to rate-limited APIs, honor a `Retry-After` header where the
API provides one, and consider a dedicated `pool` with a low concurrency
limit for tasks hitting that API so parallel DAG runs don't collectively
overwhelm it.

## Pitfalls
- Setting `retries` very high (10+) with short delays as a blanket fix --
  this can mask a real, sustained outage as "still retrying" for a long
  time before finally failing, delaying the alert that something is
  actually broken.
- Retrying on every exception type indiscriminately, including
  authentication failures or malformed-request errors that will never
  succeed no matter how many times they're retried -- this wastes the
  retry budget and delays a failure that should have surfaced
  immediately as "fix the request, not the timing."
- Adding retries at the Airflow task level while the underlying HTTP
  client *also* has its own retry logic with different backoff timing --
  the two layers compounding can produce much longer total delay before
  failure than either alone, surprising whoever is debugging why a task
  took forty minutes to fail.

## Verify
In a test environment, simulate a transient failure (point the task at a
mock endpoint that returns a 503 on the first N calls and succeeds after)
and confirm the task automatically recovers within the configured retry
window without manual intervention, while a separate test against a mock
endpoint returning a deterministic 400 confirms the task fails promptly
rather than exhausting all retries first.
