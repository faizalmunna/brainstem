---
name: scheduled-dag-run-missed-with-no-alert
description: A DAG that runs on a fixed schedule gets delayed or silently skipped because of scheduler or worker capacity limits, and no one is alerted about the missed SLA.
triggers: ["airflow dag didn't run on time", "scheduled dag missing run", "airflow tasks stuck queued", "dag delayed no alert", "airflow pool exhausted tasks not starting"]
permissions: ["READ"]
---

## Symptom
A DAG scheduled to run at a fixed time (e.g., 6am daily) either doesn't
run at all for that interval, or runs hours late, and nobody notices
until a downstream consumer asks where their data is. The Airflow UI
eventually shows the run completing (or stuck queued), but there was no
proactive alert when the expected run time passed without a completed
run.

## Likely causes
1. **`max_active_runs` on the DAG (or `max_active_tasks`/concurrency
   settings) is capping how many instances of this DAG or how many of its
   tasks can run concurrently,** and a previous run (perhaps a slow
   backfill, or a run stuck retrying) is still occupying that slot when
   the next scheduled run should start -- the new run queues silently
   instead of running.
2. **A shared resource pool (`pool` parameter) is exhausted by other
   DAGs.** Many teams' tasks compete for a limited pool (e.g., a
   `database_connections` pool sized for peak but not for simultaneous
   backfills plus scheduled runs), and tasks queue waiting for a slot with
   no indication in the DAG's own logs that the delay is external to it.
3. **Worker/executor capacity is saturated cluster-wide** (all Celery
   workers busy, or the Kubernetes executor hitting a pod quota), so
   tasks sit in the `queued` state well past their scheduled time with no
   per-DAG signal that anything is wrong -- from inside the DAG's own
   metadata everything looks "pending," which is indistinguishable from
   "about to start any second."
4. **No SLA or freshness alerting configured at all** -- `sla` parameters
   on tasks/DAGs, an external freshness monitor, or a "did this table get
   updated by 8am" check simply doesn't exist, so a late or skipped run
   produces no signal beyond the Airflow UI itself, which nobody is
   watching in real time.
5. **The DAG's schedule and `catchup` interact unexpectedly after a
   scheduler restart or a pause/unpause**, causing a run to be considered
   "already accounted for" (or conversely queued unexpectedly) in a way
   that doesn't match the on-call team's mental model of when it should
   fire.

## Diagnose
- Check `max_active_runs` on the DAG definition and query the metadata
  database (or the UI's DAG runs view) for how many runs of this DAG were
  active/running at the time the missed run should have started.
- Check whether any task in the delayed run is in `queued` state and, if
  so, check its assigned `pool` and that pool's current utilization
  (`airflow pools list` or the UI's Pools view) -- a pool at 100%
  utilization from unrelated DAGs is a direct cause, not a mystery.
- Check overall executor/worker health at the delayed time: Celery worker
  count and active task count, or Kubernetes executor pod scheduling
  events -- a cluster-wide capacity crunch will affect many DAGs
  simultaneously, which is a different fix than a single DAG's
  concurrency setting.
- Confirm whether `sla` is set on the affected tasks/DAG and whether an
  `sla_miss_callback` or equivalent external monitor exists -- if
  neither exists, the "no alert" half of the symptom is explained
  independent of the delay's root cause.

## Fix
Separate the two problems explicitly: fixing the capacity constraint, and
adding alerting so a future occurrence pages someone instead of being
discovered downstream. For capacity, size `max_active_runs`,
`max_active_tasks`, and any custom `pool` slot counts against realistic
concurrent demand (including backfills and retries, not just the steady
state), and consider whether a genuinely slow upstream task belongs in a
dedicated pool so it can't starve unrelated DAGs sharing a
general-purpose pool. For alerting, set an explicit `sla` on
time-sensitive tasks (or the DAG) with a callback that pages/notifies
distinctly from a task failure -- an SLA miss is "this didn't finish in
time," which is a different and often earlier signal than "this failed."
Where the consuming team cares about data freshness rather than DAG
mechanics, add an independent freshness check (e.g., a scheduled query
alerting if a table's max timestamp is older than expected) that doesn't
depend on Airflow's internal state at all, so a scheduler-level outage
that hides the DAG's own status doesn't also hide the alert.

## Pitfalls
- Raising `max_active_runs` or pool size as a blanket fix without
  understanding *why* the previous run was still occupying a slot --
  if a run is stuck because of a genuine bug (a hanging task, a runaway
  retry loop), adding capacity just delays the same collision rather than
  fixing it.
- Setting SLA thresholds equal to the DAG's typical runtime with no
  margin, producing constant false-positive SLA-miss pages that get
  muted -- size SLAs against the *acceptable* delay for the business use
  case, with enough margin over normal variance to be a meaningful
  signal.
- Alerting only on task failure and assuming that covers lateness --
  a task stuck in `queued` due to pool exhaustion never fails, so a
  failure-only alert stays silent through exactly this scenario.

## Verify
Reproduce the capacity constraint deliberately in a staging environment
(set a pool to 1 slot and queue two tasks that both need it, or drop
`max_active_runs` to 1 and trigger two overlapping runs), confirm the
second run visibly queues, and confirm the configured SLA-miss
notification actually fires and reaches the intended channel within the
expected window -- not just that the setting exists in the DAG file.
