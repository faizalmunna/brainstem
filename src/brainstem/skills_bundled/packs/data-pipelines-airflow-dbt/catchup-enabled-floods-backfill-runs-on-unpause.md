---
name: catchup-enabled-floods-backfill-runs-on-unpause
description: A paused DAG with catchup enabled fires a large flood of simultaneous backfill runs the moment it is re-enabled, overwhelming downstream systems.
triggers: ["airflow unpause dag runs everything at once", "catchup true flooding runs", "dag ran many times immediately after unpausing", "airflow backfill storm after re-enable", "too many concurrent dag runs after pause"]
permissions: ["READ"]
---

## Symptom
A DAG is paused for maintenance, an incident, or simply because a team
was on vacation, and is later re-enabled. Immediately, Airflow schedules
and runs every missed interval back-to-back (or as many as concurrency
limits allow) in rapid succession -- flooding downstream databases with
simultaneous load, exhausting worker pools, or (worse) applying business
logic like "send daily digest email" or "charge daily usage" once per
missed day all at once instead of the one time actually intended.

## Likely causes
1. **`catchup` is left at its default of `True`** (or explicitly set
   `True`) without the team realizing what that means operationally --
   Airflow's scheduler interprets a DAG's schedule as "one run should
   exist for every interval since `start_date`," and unpausing after a
   long gap means it now considers many intervals overdue simultaneously.
2. **No `max_active_runs` cap (or a cap high enough to not meaningfully
   limit anything)** on the DAG, so instead of catching up gradually,
   many of the missed intervals' runs launch concurrently rather than
   serially, multiplying the instantaneous load on shared resources.
3. **The DAG's tasks aren't safe to run out of real-world time order
   concurrently** -- a task that computes a running total, sends a
   notification, or calls a non-idempotent external API assumes it's the
   only instance executing "now," and several instances for different
   logical dates hitting that logic simultaneously produces wrong
   results or duplicate side effects (duplicate emails, duplicate
   charges).
4. **The pause happened without anyone documenting the intended
   resumption behavior**, so whoever re-enables the DAG doesn't know to
   first check for and clear unwanted historical runs, or to temporarily
   set `catchup=False`/use `airflow dags unpause` with care.

## Diagnose
- Check the DAG's `catchup` setting and `start_date`, and calculate how
  many scheduled intervals fall between the last successful run before
  the pause and now -- that count is exactly how many runs will fire on
  unpause if catchup is on.
- Check `max_active_runs` on the DAG -- a low or default value limits how
  many of those queued runs execute *concurrently*, but does not reduce
  the *total* number that will eventually run; confirm which of those two
  problems (concurrency spike vs. total redundant runs) is the actual
  operational concern for this DAG.
- Identify whether any task in the DAG has a real-world side effect that
  is not idempotent or not safe to fire once per missed interval after
  the fact (sending a notification, incrementing an external counter,
  calling a billing API) -- those are the tasks where a catchup flood
  causes actual business damage, not just extra compute.
- Check whether the team has a runbook step for re-enabling a
  long-paused DAG, or whether this is being discovered live during an
  actual unpause.

## Fix
Decide deliberately, per DAG, whether historical catchup is ever the
desired behavior -- for most operational/reporting DAGs where only the
current state matters, set `catchup=False` so unpausing simply resumes
from the next scheduled interval instead of replaying history. Where
catchup genuinely is needed (a DAG that must eventually process every
day's data even if delayed), keep it enabled but bound the blast radius
with a low `max_active_runs` so missed intervals process serially at a
controlled pace rather than all at once, and make sure every task in
that DAG is either idempotent (safe to run once per logical date without
double side effects) or explicitly excluded from the catch-up path (for
example, splitting "compute the historical data" from "send the
notification" into separate DAGs, so only the notification DAG is
catchup-sensitive). Before re-enabling a DAG that's been paused for an
extended period, treat it as a deliberate operation: review how many
runs will fire, and consider explicitly clearing or marking unwanted
historical DAG runs as skipped before unpausing, rather than unpausing
and reacting to whatever happens.

## Pitfalls
- Setting `catchup=False` as a reflexive fix without checking whether any
  downstream process actually depends on every historical interval
  eventually being processed -- this silently creates permanent gaps for
  the period the DAG was paused, which can be worse than a load spike if
  that data is never backfilled another way.
- Assuming `max_active_runs=1` alone makes a catchup flood safe -- it
  controls concurrency, not the eventual total number of runs or their
  side effects; a non-idempotent notification task will still fire once
  per missed day, just serially instead of in parallel.
- Re-enabling a paused DAG right before a peak-load period without
  considering that even a serialized catchup adds sustained extra load
  to shared downstream systems for as long as it takes to work through
  the backlog.

## Verify
In a test environment, pause a DAG configured the same way as the
production one, artificially advance the clock (or simply let several
scheduled intervals pass) to simulate a multi-interval gap, then unpause
it and confirm the number and pacing of resulting DAG runs matches the
intended behavior -- either zero historical replay (`catchup=False`) or a
controlled, serialized catch-up bounded by `max_active_runs`, with no
duplicate side effects from any non-idempotent task.
