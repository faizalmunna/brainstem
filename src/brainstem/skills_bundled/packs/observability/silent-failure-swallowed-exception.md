---
name: silent-failure-swallowed-exception
description: A real production failure produced no alert and barely any log trace, because the exception that caused it was caught and discarded (or logged at too low a level) instead of surfaced.
triggers: ["error was swallowed", "no alert fired for a real bug", "exception caught and ignored", "silent failure", "nothing logged for this error"]
permissions: ["READ"]
---

## Symptom

A user-visible or data-integrity bug is confirmed to have happened (via a
bug report, a data audit, or a support ticket), but there's little or no
corresponding log entry, no alert fired, and no metric moved -- reviewing
the code eventually reveals a `try/except`/`catch` block that swallowed
the exception (caught it, and either did nothing, logged at `debug`, or
logged a message with no stack trace/context).

## Likely causes

- **An exception handler was added defensively "just in case" during
  development** to prevent a crash, with a bare `except: pass` or
  equivalent, and never revisited once the immediate crash was avoided.
- **Error logging was set to a level below what's actually monitored**
  (logged at `debug`/`trace` in a pipeline that only alerts on `warn` and
  above), so the log line technically exists but is invisible to anyone
  not manually grepping historical debug logs.
- **The catch block logs a generic message without the exception object
  or stack trace** ("something went wrong"), making the log line
  unsearchable and useless for diagnosis even when someone does find it.
- **A catch-and-continue pattern was used for legitimate reasons in one
  code path** (e.g., best-effort cleanup that shouldn't fail the main
  operation) but the same pattern got copy-pasted into a path where the
  failure actually mattered and should have propagated or alerted.
- **Retried operations catch the exception on every attempt and only
  surface a final generic failure**, discarding the specific reason each
  individual attempt failed.

## Diagnose

1. Once a swallowed exception is suspected, grep the relevant code path
   for catch/except blocks and inspect each one for what it actually does
   with the caught error -- specifically whether it logs the exception
   object/stack trace (not just a static string) and at what level.
2. Check the logging pipeline's alerting configuration for the minimum
   level it monitors, and compare against the level the swallowed
   exception was actually logged at.
3. For a retried operation, check whether intermediate attempt failures
   are logged at all, or only a final rolled-up failure with the
   per-attempt detail discarded.
4. Search for the same catch pattern elsewhere in the codebase (it's
   rarely a single occurrence) -- copy-pasted defensive catch blocks tend
   to spread.

## Fix

Every catch block that isn't rethrowing should make a deliberate,
visible choice: log the full exception (object/stack trace, not a
paraphrased string) at a level the alerting pipeline actually monitors,
and/or increment a metric/counter for that specific failure type so it's
visible in aggregate even if nobody's grepping logs. For failures that
are genuinely expected and benign (a best-effort cache write that's fine
to skip), log at a low level explicitly and deliberately -- the fix isn't
"never swallow anything," it's "never swallow silently, without an
explicit decision documented in the code." For retried operations, log
each attempt's specific failure reason at a low level and the final
outcome (including whether it ultimately succeeded after retries) at a
level that's monitored.

## Pitfalls

Don't overcorrect into logging every caught exception at `error`
regardless of severity -- that reintroduces alert fatigue
(`alert-fatigue-noisy-thresholds`) for genuinely benign, expected
failures. The goal is matching the log level and alerting to the actual
severity, not maximizing volume. Also, when fixing a bare
`except: pass`, resist just adding a log line without asking whether the
exception should actually propagate/fail the operation -- sometimes
"caught and continued" was the wrong behavior entirely, not just poorly
logged.

## Verify

Deliberately reproduce the original failure condition in a non-prod
environment and confirm it now produces a searchable log entry with full
exception detail, and triggers the metric/alert appropriate to its actual
severity. Check that benign, intentionally-caught failures elsewhere
didn't get pulled up to a noisy alerting level in the process.
