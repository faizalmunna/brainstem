---
name: backfill-produces-different-results-than-live-run
description: Running a backfill for a past date range produces different or wrong output compared to when the DAG originally ran live for those dates.
triggers: ["backfill gives different results", "airflow backfill wrong data", "reprocessing old dates produces different output", "backfill not idempotent", "airflow catchup run mismatch with original"]
permissions: ["READ"]
---

## Symptom
A DAG is re-run for a historical date range (a manual backfill, a
`airflow dags backfill`, or a catchup run after a pause) and the rows it
produces for those dates don't match what was produced when the DAG
originally ran live -- different row counts, different aggregate values,
or records that reference data that didn't exist yet on the logical date.

## Likely causes
1. **Task logic calls `datetime.now()` / `today()` instead of using the
   DAG's logical/execution date.** A task that computes "yesterday" as
   `datetime.now() - timedelta(days=1)` gives a different answer when run
   live on the actual day versus run three months later as a backfill --
   the backfill run computes "yesterday" relative to when it's executed,
   not relative to the logical date it's supposed to represent.
2. **The task queries a mutable source "as of now" rather than "as of the
   logical date.**" A query like `SELECT * FROM orders WHERE created_at <
   CURRENT_DATE` pulls whatever exists in the table at run time -- for a
   backfill run months later, that includes rows inserted since, and
   possibly excludes rows that were later deleted or corrected, so the
   result reflects today's state of the world instead of the historical
   snapshot the logical date implies.
3. **Non-idempotent writes (append-only inserts without a delete/upsert
   step)** mean re-running the same logical date a second time adds a
   second copy of the same rows instead of replacing them -- this shows up
   as backfills that "produce different results" because the table now
   has duplicates layered on top of the original live run's rows.
4. **Dependency on external state that has since changed** -- a lookup
   table, a reference API, or an upstream dataset that was overwritten
   in place (no historical versioning) means the backfill computes against
   today's version of that reference data, not the version that existed
   when the DAG ran live.

## Diagnose
- Grep the DAG's task code for `datetime.now()`, `datetime.today()`,
  `pendulum.now()`, or any wall-clock call, and confirm whether the
  result is used for anything that should instead come from
  `{{ ds }}`, `{{ data_interval_start }}`, or `context["logical_date"]`.
- Check every SQL query and API call the task issues for a relative-time
  filter (`CURRENT_DATE`, `NOW()`, `INTERVAL '1 day'` without an anchor)
  versus an explicit logical-date-bound filter (`WHERE created_at >=
  '{{ data_interval_start }}' AND created_at < '{{ data_interval_end }}'`).
- Re-run one already-completed logical date in a test/staging environment
  and diff the output rows against what's currently in the production
  table for that same date -- an exact-match diff (not just row count)
  will surface value-level drift caused by upstream mutation.
- Check whether the destination table/partition is deleted or overwritten
  before the backfill writes, or whether it appends -- `INSERT` with no
  preceding `DELETE`/`MERGE` on the target partition is a strong signal.

## Fix
Treat the DAG's logical date as the single source of truth for "what time
period does this run represent," and thread it through every place the
task would otherwise reach for the wall clock. In Airflow, use the
Jinja-templated `{{ ds }}` / `{{ data_interval_start }}` /
`{{ data_interval_end }}` macros (or the `logical_date` in the task
context for Python operators) as the only source of "what date is this,"
never a fresh `datetime.now()` call inside task logic. Make writes
idempotent by construction: each task run for a given logical date should
first clear exactly the output it's responsible for (`DELETE FROM target
WHERE ds = '{{ ds }}'` or a partition overwrite) before writing, so
running the same logical date twice yields the same end state rather than
accumulating duplicates. Where the source system doesn't preserve
history (a mutable dimension table with no effective-dating), either
snapshot it daily so backfills can reference the historical snapshot, or
explicitly document that backfills for that DAG are best-effort and will
reflect current reference data -- don't let that limitation stay implicit.

## Pitfalls
- Switching to `{{ ds }}` for the write side but leaving a read-side
  query still filtered on `CURRENT_DATE` -- both sides of the task need
  to anchor to the same logical date, or the backfill still reads "now"
  data while writing to a "then" partition.
- Making writes idempotent via `DELETE + INSERT` without wrapping both in
  the same transaction: a failure between the delete and the insert
  leaves the partition empty rather than either fully old or fully new
  data.
- Assuming a `MERGE`/upsert alone solves idempotency -- if the source
  query itself is non-deterministic (unanchored to logical date), an
  idempotent write pattern just makes the wrong answer stable instead of
  fixing it.

## Verify
Pick a logical date that already ran successfully in production. Trigger
a manual backfill for that exact date in a non-production environment
pointed at a copy of the same source data frozen to that point in time
(or mock the current-time dependency), and confirm the output rows are
byte-for-byte identical to the original run's output -- not just similar
row counts.
