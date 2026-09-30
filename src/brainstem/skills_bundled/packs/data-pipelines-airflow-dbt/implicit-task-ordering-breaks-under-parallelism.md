---
name: implicit-task-ordering-breaks-under-parallelism
description: An Airflow DAG relies on tasks happening to run in a certain order rather than an explicit dependency, and it breaks once the scheduler parallelizes differently.
triggers: ["airflow tasks running out of order", "dag works sometimes fails other times", "airflow race condition between tasks", "task ran before its dependency", "flaky dag intermittent failure no code change"]
permissions: ["READ"]
---

## Symptom
A DAG has run reliably for a long time, then starts intermittently
failing (or silently producing wrong output) with no code change to the
failing task itself -- often correlated with a change elsewhere: more
worker slots added, a different executor, an unrelated task added to the
DAG, or simply variable timing under load. Two tasks that "always" ran in
a particular order relative to each other stop doing so.

## Likely causes
1. **Two tasks share a resource (a file path, a staging table, a temp
   directory) with no explicit `>>` dependency or sensor between them,**
   and one task's logic implicitly assumes the other has already run --
   this "worked" only because the scheduler happened to launch them in an
   order that satisfied the assumption, not because anything enforced it.
2. **A dependency exists in a `SubDagOperator`, `TaskGroup`, or across
   separate DAGs via a shared external resource, but is expressed only as
   documentation/convention** ("DAG B assumes DAG A finished by 3am")
   rather than as an `ExternalTaskSensor` or explicit trigger, so nothing
   in Airflow's scheduling actually knows about the relationship.
3. **Increased parallelism (more workers, higher `max_active_tasks`, or
   a switch to CeleryExecutor/KubernetesExecutor from
   SequentialExecutor) surfaces a previously-latent race** -- in a
   low-concurrency environment tasks tended to run near-serially by
   accident; higher concurrency now genuinely runs them concurrently,
   exposing the missing dependency.
4. **A dependency was declared once but later refactored away** -- for
   example a DAG was split into two, or a task was moved into a
   `TaskGroup`, and the explicit `>>` chain connecting the pieces wasn't
   preserved through the refactor, leaving two tasks structurally
   independent when they used to be chained.

## Diagnose
- Render the DAG's actual dependency graph (`airflow tasks list <dag_id>
  --tree` or the Graph view in the UI) and check whether the two tasks
  in question have any edge between them at all -- if they appear as
  parallel branches with no connecting arrow, there is no enforced
  ordering regardless of what the code "usually" does.
- Search both tasks' implementations for a shared resource reference
  (the same file path, the same table name written by one and read by
  the other, a shared temp/staging location) that isn't mediated by an
  Airflow dependency, sensor, or XCom.
- Check recent changes to DAG-level concurrency settings
  (`max_active_tasks`, executor type/config, worker count) around the
  time the intermittent failures began -- a timing-correlated change to
  concurrency is strong evidence this is a latent race being newly
  exposed rather than a new bug.
- Force a reproduction by manually skewing task start order in a test
  environment (e.g., add an artificial delay to the task that's supposed
  to run first) and confirm the downstream task fails or misbehaves when
  it runs before its actual prerequisite.

## Fix
Make every real dependency explicit in the DAG's structure rather than
relying on incidental scheduling behavior. Where one task's output feeds
another directly, connect them with `>>` (or `set_downstream`/
`set_upstream`) so the scheduler enforces the order regardless of
available parallelism. Where the dependency crosses DAGs, use an
`ExternalTaskSensor` (or a data-aware `Dataset`/asset trigger in newer
Airflow versions) so the downstream DAG actually waits on a signal from
the upstream one instead of assuming a timing relationship holds.
Where two tasks share a resource but don't have a natural producer/
consumer relationship, consider whether they should be merged into one
task, or whether the resource should be namespaced per-run (e.g., a
run-specific temp path keyed on `{{ run_id }}`) so concurrent runs can't
collide on it even without an explicit order.

## Pitfalls
- "Fixing" the race by adding a fixed `sleep()` or a coarse
  `trigger_rule` tweak instead of an actual dependency edge -- this
  narrows the failure window without closing it, and it will reappear
  under different load or on a slower environment.
- Adding an `ExternalTaskSensor` with a default execution-date match
  when the two DAGs run on different schedules -- the sensor can wait
  for a logical date that will never produce a matching run, hanging
  indefinitely; the `execution_date_fn` needs to map schedules correctly.
- Serializing everything into one long linear chain "to be safe" once a
  race is found, destroying legitimate parallelism for unrelated tasks
  that never actually needed ordering.

## Verify
After adding the explicit dependency, inspect the DAG's Graph view to
confirm a direct edge now connects the two tasks, then run the DAG
repeatedly under the same high-concurrency configuration that originally
exposed the race (same worker count, same `max_active_tasks`) and confirm
the previously-intermittent failure no longer occurs across multiple
consecutive runs.
