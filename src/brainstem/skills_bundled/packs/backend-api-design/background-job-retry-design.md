---
name: background-job-retry-design
description: Design safe retry/backoff behavior for background jobs (Celery/Sidekiq/BullMQ/etc.) so retries don't duplicate side effects or overwhelm a struggling downstream service.
triggers: ["background job retry", "job runs twice", "celery task duplicated", "retry storm", "job keeps failing and retrying", "duplicate side effect from retry"]
permissions: ["READ"]
---

## Symptom
Either: a background job's side effect (an email, a charge, a downstream
API call) happens more than once because the job was retried after a
partial failure, or a struggling downstream dependency gets hit with a
retry storm that makes its outage worse instead of the system backing off.

## Likely causes
1. **A job that isn't idempotent** performing a non-idempotent side
   effect, retried after a failure that happened *after* the side effect
   already completed (e.g. the job sent the email successfully but then
   crashed before marking itself done, so the queue retries it from the
   top).
2. **Fixed-interval or immediate retries with no backoff**, so a
   struggling downstream service gets hit again immediately and
   repeatedly by every failing job, amplifying the outage instead of
   giving it room to recover.
3. **No maximum retry count / dead-letter handling**, so a
   permanently-failing job (bad input, a bug) retries forever, consuming
   worker capacity that healthy jobs need.
4. **Retrying on the wrong class of failure** -- retrying a 4xx
   client-error response (which will never succeed on retry) the same
   way as a 5xx/timeout (which might), wasting retries on unfixable
   failures.

## Diagnose
- Check whether the job's side effect is idempotent (see
  `api-idempotency-keys` for the general pattern) -- specifically, could
  running the exact same job body twice with the same input produce a
  duplicated real-world effect?
- Check the retry configuration: interval type (fixed vs. exponential
  backoff with jitter), maximum attempts, and whether there's dead-letter
  queue/alerting for jobs that exhaust their retries.
- Check whether the failure-handling logic distinguishes retryable
  failures (timeouts, 5xx, connection errors) from non-retryable ones
  (validation errors, 4xx responses, business-logic rejections).

## Fix
- Make the job idempotent at the point of the side effect: record what's
  already been done (e.g. "email for order #123 already sent") before or
  atomically with doing it, and check that record at the start of every
  attempt (including the first) so a retry after a partial failure is a
  safe no-op for the part that already succeeded.
- Use exponential backoff with jitter between retries (not fixed
  intervals), so retries spread out over time instead of synchronizing
  into repeated bursts against a struggling dependency.
- Set a maximum retry count with a dead-letter queue (or equivalent
  failed-job table) for jobs that exhaust retries, with alerting -- so
  permanently-failing jobs are surfaced for human investigation instead
  of retrying silently forever or disappearing.
- Classify failures explicitly: don't retry validation/4xx-style failures
  that will never succeed on retry; do retry timeouts/5xx/connection
  errors, with backoff.

## Pitfalls
- Making a job "idempotent" by just checking "has this job ID run before"
  doesn't help if the job ID changes on each retry (some queue systems
  generate a new attempt ID) -- key the idempotency check on the
  *business* operation (order ID, email recipient+template+order),
  not the queue's internal attempt/job ID.
- Aggressive backoff without a cap on the interval can delay legitimate
  recovery for hours after a brief outage -- cap the maximum backoff
  interval, don't let it grow unbounded.
- Dead-lettering a job silently (no alert) just moves the "retries
  forever" problem into "fails forever, unnoticed" -- pair dead-lettering
  with actual alerting/visibility.

## Verify
Simulate a downstream failure (e.g. point the job at a deliberately
failing/slow endpoint) and confirm: retries back off exponentially rather
than hammering immediately, the job's side effect doesn't duplicate if it
partially succeeded before failing, and the job lands in a visible
dead-letter state after exhausting its retry budget rather than retrying
indefinitely.
