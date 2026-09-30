---
name: dbt-incremental-model-duplicate-or-missing-rows
description: A dbt model built with incremental materialization silently accumulates duplicate rows or drops late-arriving records over time.
triggers: ["dbt incremental model duplicate rows", "dbt incremental missing late data", "dbt is_incremental filter wrong", "incremental model row count growing unexpectedly", "dbt model has more rows than source"]
permissions: ["READ"]
---

## Symptom
A dbt model using `materialized='incremental'` looks correct right after
being built from scratch (`--full-refresh`), but after running
incrementally for weeks, its row count no longer reconciles with the
source table -- either duplicate rows accumulate for records that were
updated more than once, or records that arrived a day or two late never
show up at all, even though they exist in the source.

## Likely causes
1. **The `is_incremental()` filter uses a fixed lookback window that's
   narrower than real-world data latency** -- a filter like `WHERE
   updated_at > (SELECT max(updated_at) FROM {{ this }})` only picks up
   rows newer than the last run's max timestamp, so a row that arrives
   late (e.g., a mobile event synced two days after it occurred, with an
   original `updated_at` older than the current watermark) is permanently
   skipped because it will never again be "newer than max" once later
   rows have pushed the watermark past it.
2. **The incremental strategy is `append` when the underlying data can be
   updated in place** -- `append` only ever adds rows and has no concept
   of "this is an update to a row I already have," so any source record
   that gets updated after its first incremental run produces a second,
   duplicate row rather than replacing the first.
3. **The unique key for a `merge`/`delete+insert` strategy doesn't
   actually uniquely identify the grain of the model,** so the merge
   matches on a key that isn't unique, causing either unintended overwrite
   of unrelated rows or, with certain adapters, duplicate insertion when
   multiple source rows share the declared "unique" key.
4. **A `--full-refresh` and a normal incremental run disagree on logic**
   because the `{% if is_incremental() %}` branch's filter and the
   non-incremental branch's base query aren't actually computing the same
   thing -- the full-refresh path might include a join or dedup step the
   incremental path skips, so the two build modes silently diverge over
   time.

## Diagnose
- Read the model's `is_incremental()` block and identify exactly what
  column and comparison it filters on, then ask: what is the maximum
  realistic delay between a row's business timestamp and when it lands
  in the source table? If that delay can exceed the filter's lookback,
  late rows are being dropped by design.
- Check the configured `incremental_strategy` (`append`, `merge`,
  `delete+insert`, `insert_overwrite`) against whether source rows can
  ever be updated after their first appearance -- `append` is only
  correct for genuinely immutable, insert-only sources.
- Run `SELECT unique_key_column, COUNT(*) FROM model GROUP BY 1 HAVING
  COUNT(*) > 1` against the built model to directly surface duplicates,
  and separately compare `COUNT(DISTINCT id)` between the source and the
  incremental model for a fixed historical window to surface missing
  rows.
- Diff the full-refresh SQL path against the incremental SQL path in the
  model file line by line -- any join, filter, or dedup logic present in
  one branch but not the other is a likely source of drift between a
  freshly rebuilt table and one that's been running incrementally.

## Fix
Widen the incremental filter to a lookback window that comfortably covers
observed late-arrival latency rather than a bare "since last max
timestamp" -- for example, `WHERE updated_at >= (SELECT max(updated_at) -
INTERVAL '3 days' FROM {{ this }})` reprocesses a safety window of recent
history on every run, trading a bit of extra compute for closing the
late-arrival gap. Pair that wider filter with an incremental strategy
that can actually reconcile reprocessed rows rather than duplicating them
-- `merge` or `delete+insert` keyed on the true business unique key (not
just a load-timestamp) makes reprocessing the safety window idempotent:
rows that already exist get updated in place rather than duplicated.
Where a `unique_key` is declared, make sure it's independently verified
unique at the grain of the model (test it with a dbt `unique` test on
that exact column combination) so the merge behaves as intended rather
than silently matching the wrong rows.

## Pitfalls
- Widening the lookback window without switching away from `append`
  strategy -- this makes duplicates *worse*, not better, since now the
  same already-loaded rows are being reprocessed and re-appended every
  run instead of merged.
- Making the lookback window so wide that it effectively reprocesses most
  of the table on every run, defeating the performance purpose of
  incremental materialization in the first place -- size the window
  against measured late-arrival latency, not an arbitrarily large "to be
  safe" number.
- Declaring a `unique_key` that's technically unique in current data but
  not guaranteed unique by the source system's own constraints -- a
  future schema or data change can silently violate that assumption and
  reintroduce duplicates or overwrite bugs.

## Verify
Run `dbt build --full-refresh` to get a known-correct baseline, record
its row count and a checksum/hash of key aggregate columns, then run the
model incrementally forward across several days including at least one
day with deliberately delayed test data, and confirm the incrementally
built table's row count and aggregates match a fresh full-refresh over
the same date range exactly.
