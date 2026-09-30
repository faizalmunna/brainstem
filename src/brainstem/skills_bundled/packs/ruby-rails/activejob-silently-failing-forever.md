---
name: activejob-silently-failing-forever
description: Diagnose a Sidekiq or ActiveJob background job that keeps failing and retrying indefinitely without ever alerting anyone.
triggers: ["sidekiq job stuck retrying", "job failing silently in background", "sidekiq retry set growing", "activejob never completes", "background job errors not showing up anywhere"]
permissions: ["READ"]
---

## Symptom
A background job (Sidekiq, or ActiveJob on any adapter) has been failing
and retrying for hours or days, visible only if someone happens to open
the Sidekiq Web UI's Retries tab or query the jobs table directly --
no error tracker entry, no on-call alert, and often no user-facing symptom
until whatever the job was supposed to do (send an invoice, sync a record)
is noticed missing much later.

## Likely causes
1. **The job (or code it calls) rescues the exception internally and logs
   it instead of re-raising**, so Sidekiq/ActiveJob sees the job as
   "succeeded" and never retries -- or the opposite: it re-raises but the
   error tracker (Sentry/Honeybadger/Rollbar) integration isn't wired up
   for the job-processing context, only for web requests, so exceptions
   from workers never reach it.
2. **`retry_on`/Sidekiq's default retry (25 attempts over ~21 days) is
   configured with no `discard_on` or dead-set alerting**, so a
   permanently-failing job (bad data, a removed record, a typo'd API
   endpoint) just keeps retrying on an exponential backoff for weeks,
   silently, because "still retrying" looks identical to "healthy" from
   outside.
3. **The job fails fast enough, and often enough, to get pushed to
   Sidekiq's dead set (after exhausting retries) with no monitoring on
   the dead set size/growth** -- dead jobs are retained but nothing pages
   anyone when the count grows.
4. **The exception is a subclass explicitly excluded from a global
   `Sidekiq::Client` or ActiveJob error-reporting middleware/hook**
   (a deliberate `rescue SpecificError` added for one edge case that's
   now swallowing a broader class of failures than intended).

## Diagnose
- Open Sidekiq Web UI's Retries and Dead tabs (or run
  `Sidekiq::RetrySet.new.size` / `Sidekiq::DeadSet.new.size` in a console)
  and check the actual counts and how long jobs have been retrying --
  confirm this is a systemic pattern, not one flaky job.
- Pick one failing job instance and read its stored error message/backtrace
  directly from Sidekiq's retry payload (`Sidekiq::RetrySet.new.first.item["error_message"]`)
  rather than assuming -- confirm what exception is actually being raised
  and whether it's retryable at all (e.g. a `RecordNotFound` for a
  permanently deleted row will never succeed on retry).
- Grep the job class and everything it calls for `rescue` blocks that
  swallow exceptions (`rescue => e; logger.error(e); end` with no
  re-raise) -- this is the most common reason nothing ever surfaces.
- Check the error tracker's configuration for whether it hooks into the
  job-processing lifecycle specifically (Sidekiq has a documented error
  handler hook: `Sidekiq.configure_server { |c| c.error_handlers << ... }`;
  ActiveJob has `rescue_from`/`retry_on` plus `around_perform`) -- confirm
  it's not only wired into the Rails exception middleware, which never
  sees background-job errors.

## Fix
- Wire the error tracker explicitly into the job runtime: for Sidekiq,
  add a server-side error handler
  (`config.error_handlers << ->(ex, ctx) { Sentry.capture_exception(ex, extra: ctx) }`);
  for ActiveJob, ensure the adapter's failure hook or an `around_perform`
  reports every unhandled exception before it's swallowed by the retry
  mechanism.
- Classify failures in the job itself: use `retry_on` for genuinely
  transient errors (timeouts, connection errors) with a bounded number of
  attempts and explicit backoff, and `discard_on` (or an equivalent
  immediate-fail path) for errors that will never succeed on retry
  (record not found, validation failure) -- and make `discard_on` also
  report to the error tracker before discarding, since "discarded" should
  not mean "silent."
- Add monitoring on the retry/dead set itself, independent of individual
  job outcomes: alert when `Sidekiq::DeadSet.new.size` or the retry
  queue's age crosses a threshold, so a class of permanently-failing jobs
  is caught even if each individual failure was reported.
- Remove overly broad `rescue` blocks inside job code; if a specific
  exception must be handled softly, catch that exact class, log it with
  enough context to act on, and still report it to the tracker at a lower
  severity rather than discarding it entirely.

## Pitfalls
- Adding blanket alerting on every single retry (not just exhausted/dead
  jobs) creates alert fatigue for jobs that succeed on their second
  attempt due to normal transient network blips -- alert on sustained
  failure (dead set growth, or N consecutive failures for the same job
  type) rather than every retry.
- Increasing the retry count "to be safe" without adding dead-set
  alerting just delays when the silent failure becomes visible, from
  hours to weeks -- more retries is not a substitute for observability.
- Fixing the reporting gap for the job you found without checking sibling
  job classes for the same missing hook -- the error-handler wiring is
  usually missing globally, not per-job, so verify the fix at the
  Sidekiq/ActiveJob configuration level, not just in one job file.

## Verify
Force a job to fail deliberately (e.g. temporarily point it at a
non-existent endpoint or raise in a test-only branch) in a
staging/sandbox environment and confirm: the error tracker receives an
event with the job's context, the job follows the intended retry
classification (bounded retries with backoff, or immediate discard for
non-retryable errors), and, after exhausting retries, it appears in the
dead set with an alert fired -- not just a silent entry.
