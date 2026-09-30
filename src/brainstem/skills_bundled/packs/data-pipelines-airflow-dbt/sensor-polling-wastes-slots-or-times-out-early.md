---
name: sensor-polling-wastes-slots-or-times-out-early
description: An Airflow sensor waiting for an upstream file or table either occupies a worker slot inefficiently while polling or times out before the data actually arrives.
triggers: ["airflow sensor timing out too early", "sensor using up all worker slots", "airflow filesensor blocking pool", "sensor poke interval wrong", "airflow waiting for upstream data times out"]
permissions: ["READ"]
---

## Symptom
A DAG has a sensor task waiting on an external condition -- a file
landing in storage, a partition appearing in a table, an upstream API
reporting readiness. Either the sensor is one of two problems: it ties up
a worker slot for hours doing nothing but polling, starving other tasks
that need that slot, or it times out and fails *before* the upstream data
actually became available, forcing a manual retry once the real data
finally shows up minutes later.

## Likely causes
1. **The sensor runs in default `poke` mode, which occupies a full
   worker slot for its entire wait duration** -- a sensor waiting three
   hours for a file holds a worker slot idle-but-allocated for all three
   hours, and enough long-running sensors like this across a deployment
   can exhaust worker capacity for unrelated tasks that would otherwise
   run in seconds.
2. **`timeout` is set shorter than the realistic (not average-case)
   latency of the upstream dependency** -- if the upstream file/table
   normally lands by 6am but occasionally, legitimately, lands as late as
   8am, a sensor with `timeout` tuned to "a bit past the typical case"
   will intermittently fail on exactly the days when the data was simply
   running late but still arriving correctly.
3. **`poke_interval` is set too aggressively low** for what's being
   checked, hammering the external system (an object store's list API, a
   database) with far more frequent checks than necessary, which can
   itself contribute to rate-limiting or cost, especially at scale across
   many parallel sensor instances.
4. **The sensor checks for the wrong signal of "ready"** -- for example,
   checking only that a file exists rather than that it's fully written
   (a file can appear in a listing while still being uploaded/streamed),
   causing the sensor to succeed and hand off to a downstream task that
   then reads a truncated or partial file.

## Diagnose
- Check the sensor's `mode` parameter -- if it's absent or explicitly
  `poke` and the expected wait time is long (tens of minutes or more),
  that's a direct architectural mismatch; `poke` mode is intended for
  short waits.
- Compare the sensor's configured `timeout` against the actual historical
  distribution of upstream arrival times (not just the typical/median
  case) -- pull several weeks of the upstream system's actual delivery
  timestamps and check whether the configured timeout covers the
  legitimate tail, not just the common case.
- Check `poke_interval` against how expensive/rate-limited the check
  itself is -- listing a cloud storage prefix or querying a busy
  database every few seconds for hours is a different cost profile than
  checking a lightweight metadata endpoint.
- Read exactly what condition the sensor checks (existence vs. a
  completeness marker like a `_SUCCESS` file, a specific row count, or a
  partition-registered event) and confirm it actually corresponds to
  "the data is fully ready to consume," not just "something showed up."

## Fix
For waits longer than a few minutes, switch the sensor to `mode="reschedule"`,
which releases the worker slot between pokes instead of holding it for
the entire wait -- the sensor's task instance goes to a scheduled/up-for-
reschedule state between checks rather than occupying a slot the whole
time, which is the correct default for anything waiting on
external, unpredictable timing. Set `timeout` against the observed
realistic tail of upstream latency (with margin), not the average case,
and treat a sensor timeout as an actionable alert precisely because it
means the wait exceeded even the generous, tail-aware bound. Set
`poke_interval` proportional to how time-sensitive the downstream
consumer actually is and how expensive the check is -- a multi-minute
interval is usually fine for an hours-long wait. Most importantly, make
the sensor check an actual completeness signal (a `_SUCCESS`/marker file
written last by the producer, a row count matching an expected value, a
partition-registration event) rather than mere existence of the primary
data file, so "sensor succeeded" reliably means "safe to consume," not
just "something is there."

## Pitfalls
- Switching to `mode="reschedule"` without accounting for its coarser
  scheduling granularity -- reschedule mode's checks happen on the
  scheduler's own cadence, so it's not appropriate for waits needing
  sub-minute precision; that's a legitimate case to keep `poke` mode with
  a short timeout instead.
- Widening `timeout` generously to reduce false failures without adding
  any alerting for "the sensor is taking much longer than usual" --
  this trades false failures for silent lateness, reintroducing the
  missed-SLA-with-no-alert problem in a different form.
- Using an `ExternalTaskSensor` or file sensor as a substitute for fixing
  a genuinely unreliable upstream schedule, rather than also pushing to
  make the upstream producer's timing more predictable where that's
  feasible.

## Verify
Trigger the DAG in a test environment and confirm, via the Airflow UI's
task instance details, that the sensor's task state cycles through
`up_for_reschedule` between checks (not continuously `running`) if using
reschedule mode, and separately confirm the worker slot is available for
other queued tasks during the sensor's wait rather than blocked.
Additionally, replay several historical "late but legitimate" arrival
scenarios and confirm the sensor's timeout no longer fails on them.
