---
name: aspnet-hostedservice-silent-exit
description: Diagnose an ASP.NET Core background IHostedService that stops running permanently after an unhandled exception with no log or alert.
triggers: ["background service stopped running", "ihostedservice died silently", "backgroundservice exception not logged", "scheduled job stopped executing after a while", "hosted service exited without error"]
permissions: ["READ"]
---

## Symptom
A background worker (`IHostedService`/`BackgroundService`) that's
supposed to run continuously or on a recurring schedule (polling a
queue, running periodic cleanup, processing an outbox table) simply stops
doing its work at some point, with the rest of the application (the web
server, other requests) continuing to run normally. There's no crash, no
obvious error in the logs pointing at the worker, and often no
alert fires because "the app is still up" from a health-check
perspective -- only a business-level symptom appears later (a queue
backs up, a scheduled cleanup never ran, stale data accumulates).

## Likely causes
1. **An unhandled exception escapes `ExecuteAsync` in a
   `BackgroundService`** -- the .NET hosting infrastructure catches the
   exception, marks the service's execution task as faulted, and (by
   default) does not automatically restart it or crash the whole process
   -- the service just silently never runs again for the remaining
   lifetime of the app, and unless something explicitly observes the
   faulted task, nothing logs it.
2. **The exception is caught inside the worker's own loop but the catch
   block only logs at a level nobody monitors (or doesn't log at all)**
   and then the loop exits instead of continuing to the next iteration --
   e.g. a `try/catch` around the per-item processing logic that's
   accidentally placed around the whole `while` loop instead of inside
   each iteration, so one bad message/item ends the service entirely
   instead of just failing that one unit of work.
3. **`Host.CreateDefaultBuilder`'s `BackgroundServiceExceptionBehavior`
   is left at its default (`StopHost`) or set to `Ignore` without
   understanding the tradeoff** -- depending on the configured behavior
   and .NET version, an unhandled exception from a hosted service either
   stops the entire host (loud, but maybe not desired if other hosted
   services/the web server should keep running) or is ignored entirely
   (quiet, and exactly this symptom) -- teams sometimes set it to
   `Ignore` specifically to "keep the app up" without realizing that also
   means the failed service never runs again and nothing surfaces the
   failure.
4. **The service's `Task` is awaited nowhere**, so nothing in the app
   ever observes whether it faulted -- `IHostedService.StartAsync` is
   expected to return quickly while the actual work runs on a
   fire-and-forget task internally (this is normal for
   `BackgroundService`), but if application code elsewhere also spawns
   unobserved tasks related to the worker, those can fault silently the
   same way, compounding the diagnosis.

## Diagnose
- Check whether the worker wraps its entire `while (!stoppingToken.
  IsCancellationRequested)` loop body in a try/catch, or only wraps
  individual units of work -- a catch outside the loop that doesn't
  re-enter the loop after logging is a direct match for cause 2.
- Check the app's configured `BackgroundServiceExceptionBehavior` (via
  `services.Configure<HostOptions>(o => o.BackgroundServiceExceptionBehavior
  = ...)`) -- confirm what actually happens on an unhandled exception in
  this app: process exit, or silent continuation with the faulted service
  dead.
- Add a diagnostic log statement immediately before and after the
  worker's main loop body, plus a top-level try/catch around the entire
  `ExecuteAsync` that logs at `Error` level with the full exception before
  rethrowing (or handling) -- deploy this to reproduce or confirm which
  exception is escaping and when.
- Check whether the application has any health check or liveness probe
  that specifically reflects hosted-service health (most default
  `/health` endpoints only reflect the web server's ability to respond,
  not whether background services are still executing) -- confirm this
  gap is why no alert fired.
- Correlate the last successful iteration's log timestamp (if any
  periodic "heartbeat" log exists) with when the downstream symptom
  (queue backlog, stale data) started, to pin down when the service
  actually died versus when it was noticed.

## Fix
- Wrap each unit of work inside the loop in its own try/catch (not the
  loop itself), log the exception with full context (item/message ID,
  stack trace) at `Error` level, and continue to the next iteration --
  one bad item should not end the whole worker.
- Add a top-level try/catch around `ExecuteAsync`'s outer loop that logs
  a `Critical`-level "background service has stopped unexpectedly"
  message with the exception before the method returns, so there is
  always at least one loud log entry marking the service's death,
  regardless of what killed the inner loop.
- Add a dedicated health check that reflects hosted-service liveness --
  e.g. the worker updates a timestamp/counter on each successful
  iteration, and a custom `IHealthCheck` fails if that timestamp is older
  than the expected interval, so monitoring can alert on "the worker
  stopped," not just "the process is up."
- Decide deliberately (not by leaving the default) what
  `BackgroundServiceExceptionBehavior` should be for this app, and pair
  whichever choice is made with the logging/health-check changes above --
  `StopHost` at least makes the failure loud (the whole app restarts, and
  orchestration/monitoring notices), while `Ignore` requires the
  heartbeat health check to be in place or failures go unnoticed exactly
  as in this symptom.

## Pitfalls
- Wrapping the exception in an infinite retry-forever loop without a
  backoff or a failure cap turns a silent death into a silent infinite
  failure loop instead -- pair per-iteration error handling with a
  backoff strategy and a circuit-breaker/alert threshold so persistent
  failures are surfaced, not just survived indefinitely.
- Logging the exception but still allowing `ExecuteAsync` to return
  afterward doesn't fix the underlying stoppage -- if the intent is for
  the worker to keep running, the fix must keep the loop iterating after
  logging, not just make the eventual stop more visible.

## Verify
Inject a deliberate exception into a single simulated unit of work in a
test/staging environment and confirm: (1) the worker logs the error at
the intended severity, (2) the worker continues processing subsequent
items rather than exiting, and (3) if a heartbeat health check was added,
briefly stopping the worker's loop causes that health check to report
unhealthy within the expected staleness window.
