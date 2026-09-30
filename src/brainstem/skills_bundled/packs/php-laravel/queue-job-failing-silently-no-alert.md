---
name: queue-job-failing-silently-no-alert
description: A queued job throws an exception, lands in the failed_jobs table, and nobody on the team finds out until a customer reports missing data.
triggers: ["failed_jobs table filling up", "queue job silently failing", "laravel job never ran and nobody noticed", "no alert on failed job"]
permissions: ["READ"]
---

## Symptom
A queued job (an email, a webhook relay, a report generation) throws an
exception, exhausts its retries, and gets written to the `failed_jobs`
table -- but the application behaves as if nothing happened. There's no
error in the request/response cycle (the job runs out-of-band), no alert
fires, and the failure is only discovered when a human notices the
downstream effect never happened, often days later.

## Likely causes
1. **No `failed()` handling or listener is registered at all** -- Laravel
   writes to `failed_jobs` by default, but that table is a passive log,
   not an alert; without an explicit `Queue::failing()` listener, a
   `failed()` method on the job class, or a monitoring integration reading
   that table, nothing notifies anyone.
2. **`Queue::failing()` is registered but only logs**, e.g.
   `Log::error($event->exception)`, into a log file nobody is watching --
   technically "handled," but functionally silent because the log sink
   isn't wired to an alerting channel (Slack, PagerDuty, email digest).
3. **The job is being retried in a way that masks the true failure state**
   -- `--tries` is set high with no `retryUntil()`/backoff, so the job
   keeps quietly retrying for a long time before it ever reaches
   `failed_jobs`, and by the time it does, the person who could act on it
   has moved on to other work with no record connecting the delay to this
   job.
4. **Horizon (or a supervisor) isn't actually monitoring the failed queue**
   -- if using Horizon, its dashboard shows failures, but nobody has
   Horizon's Slack/email notification configured
   (`Horizon::routeMailNotificationsTo()` / `routeSlackNotificationsTo()`),
   so the dashboard exists but nobody looks at it proactively.
5. **The exception is being swallowed inside the job's `handle()` method**
   by a broad `try/catch` that logs and returns normally instead of
   re-throwing -- the job then reports success to the queue, never reaches
   `failed_jobs` at all, and is strictly worse than the other causes
   because there's no record anywhere that anything went wrong.

## Diagnose
- Query `failed_jobs` directly (`SELECT * FROM failed_jobs ORDER BY
  failed_at DESC`) to confirm whether failures are actually landing there
  -- if the job's effect is missing but the table is empty, suspect cause
  5 (a swallowed exception inside `handle()`).
- Check `config/queue.php` and `App\Providers\*` (or `bootstrap/app.php`
  on Laravel 11+) for a `Queue::failing()` listener -- if none exists,
  that's the gap.
- If a listener exists, trace where it sends its output: a bare `Log::`
  call with no alerting integration downstream is equivalent to no
  listener for the purpose of getting a human's attention in time.
- If using Horizon, check `config/horizon.php` for
  `notifications.slack`/`notifications.mail` config being unset or
  pointing at an address/channel nobody monitors.
- Grep the job's `handle()` method for a `try { ... } catch (\Throwable $e)
  { Log::error($e); }` block that doesn't `throw $e;` -- this is the
  single most common cause of a queue failure with zero trace anywhere.

## Fix
- Re-throw inside job-level try/catch blocks unless the catch is doing
  something specific and intentional (like converting one exception type
  to another) -- a job's `handle()` should let unexpected exceptions
  propagate so the queue's own failure machinery (`failed_jobs`, retry
  count, `failed()` hook) can do its job.
- Implement `failed(Throwable $exception)` on jobs that have a
  business-meaningful failure mode (a payment job, an email that
  confirms an order) to trigger a direct, specific alert (notify an
  admin, flag the record for manual follow-up) rather than relying only
  on the generic `failed_jobs` table.
- Wire a global `Queue::failing()` listener (in a service provider's
  `boot()`) to an actual paging/alerting channel -- a Slack webhook
  notification or a monitoring tool's error-tracking integration (e.g.
  reporting the exception the same way `report()` would) -- so any job
  failure across the app surfaces without needing every job author to
  remember to add per-job alerting.
- If using Horizon, configure `notifications.slack`/`mail` in
  `config/horizon.php` pointed at a channel the on-call rotation actually
  watches, and set `Horizon::night()`/dashboard access as a secondary,
  not primary, detection method.

## Pitfalls
- Alerting on every single failed job, including ones with legitimate,
  expected, non-retryable failures (bad user input, a client-side
  validation gap), trains the team to ignore the alert channel -- classify
  failures (see the general retry-design pattern) and only page for the
  ones that indicate a real problem, not user error.
- Adding `Queue::failing()` alerting but leaving `--tries=1` with no
  backoff means transient failures (a downstream API blip) alert
  immediately on the first hiccup instead of after a reasonable retry
  budget -- pair alerting with sane retry/backoff so alerts mean "this
  genuinely didn't work," not "it failed once."
- Treating `failed_jobs` as a queue of work to manually re-run via
  `artisan queue:retry` without first fixing the root cause reproduces the
  same failure on retry and just moves the noise around -- diagnose why it
  failed before retrying it.

## Verify
Force a job to fail deliberately (throw in a test job, or point a
downstream call at an invalid endpoint in staging), and confirm three
things end-to-end: the job appears in `failed_jobs`, the configured alert
(Slack message, PagerDuty page, monitoring-tool error event) actually
fires and is visible to whoever is on call, and the alert contains enough
context (job class, exception message, relevant model ID) to act on
without needing to dig through logs first.
