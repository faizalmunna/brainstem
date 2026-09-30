---
name: task-succeeds-but-output-data-incomplete
description: An Airflow task reports success and turns green but the data it produced is incomplete or wrong, and nothing catches it before downstream consumption.
triggers: ["airflow task succeeded but data is wrong", "dag green but bad data downstream", "task passed but rows missing", "silent data quality failure airflow", "downstream dashboard wrong but pipeline shows success"]
permissions: ["READ"]
---

## Symptom
The Airflow UI shows every task in the DAG as green, no errors in the
logs, and the run completes on schedule -- but a downstream dashboard,
report, or consuming team finds the data is incomplete (a partition with
half the expected rows, a join that silently dropped unmatched records,
a source that returned an empty result set that got treated as valid).
The pipeline's notion of "success" and the data's actual correctness have
diverged.

## Likely causes
1. **Task success is defined purely by "the process exited zero,"** not
   by anything about the data produced -- a Python operator that catches
   an exception, logs a warning, and returns normally, or a SQL script
   that runs a `MERGE` against an accidentally empty source table, both
   complete "successfully" while producing wrong output.
2. **No data-quality assertions gate the DAG's success/downstream
   trigger** -- row-count checks, null-rate checks, freshness checks, or
   referential checks (dbt tests or an equivalent) exist nowhere in the
   DAG, so there's no mechanism that *could* have failed the run even if
   one were warranted.
3. **An upstream source silently returned partial data** (an API
   pagination bug that only fetched page 1, a file landing "on time" but
   truncated mid-write, a change-data-capture feed that dropped a batch)
   and the extraction task has no expectation of a specific volume or
   shape to compare against.
4. **A join or filter step silently drops rows instead of failing loud**
   -- an inner join against a dimension table with missing keys quietly
   excludes fact rows rather than surfacing them as an error, and nobody
   is comparing input row count to output row count.

## Diagnose
- Check whether the DAG has *any* task whose only job is validating the
  data just produced (row count within an expected range, no unexpected
  nulls in required columns, referential integrity against a dimension)
  -- if the answer is "no such task exists," that's the root gap, not a
  bug in a specific task.
- Compare the row count/date range actually loaded for the affected run
  against the historical average for that same DAG/table on comparable
  days -- a sudden drop (e.g., 40% of normal volume) that nothing alerted
  on confirms the pipeline has no volume-based check.
- Trace the specific incomplete data back to its extraction task's logs:
  look for a caught-and-swallowed exception, an API response that was
  empty or paginated incoretrly, or a silently-empty intermediate
  DataFrame/table that later steps operated on without checking `if
  len(df) == 0`.
- Check the join/transform step that touches the affected data for an
  inner join or `WHERE` filter that would silently exclude rows rather
  than erroring when a expected key is missing.

## Fix
Add explicit data-quality checks as first-class tasks in the DAG (or as
dbt tests gating a `dbt build`), and make them structurally able to fail
the run and block downstream consumption -- not just log a warning. A
practical pattern: after each extraction/load task, add a lightweight
"assert" task that checks row count against a sane bound (e.g., "at
least X% of the trailing 7-day average"), checks required columns for
unexpected null rates, and checks any known key relationships, then wire
it with `>>` so downstream tasks are set to `all_success` and won't run
if the check fails. In dbt, this means running `dbt test` (or `dbt
build`, which interleaves models and tests and halts dependents when a
test fails) as part of the orchestrated pipeline, not as a
disconnected nightly job whose failures nobody is watching. For
tasks that call external sources, validate the *shape* of what came back
(non-empty, expected schema, expected approximate volume) before treating
extraction as done, rather than trusting "the HTTP call returned 200."

## Pitfalls
- Adding data-quality checks that are so strict they page on every minor,
  harmless fluctuation -- this trains people to ignore or silence the
  alerts, which recreates the original silent-failure problem with extra
  steps. Calibrate thresholds against real historical variance, not
  guessed round numbers.
- Adding the check task but not actually wiring it into the dependency
  graph as a blocking gate (leaving it as an informational task that runs
  in parallel with, rather than before, downstream consumers) -- it will
  report failures but not prevent the bad data from being consumed.
- Checking row counts but not null rates or referential integrity --
  a task can produce exactly the expected number of rows while every
  value in a critical column is null because of a broken join.

## Verify
Deliberately feed the pipeline a known-bad input in a test environment
(truncate a source file to zero rows, or point the extraction task at an
empty date range) and confirm the new data-quality task fails and that
failure actually prevents the downstream task from running (check its
Airflow state is `upstream_failed` or `skipped`, not that it silently
executed anyway).
