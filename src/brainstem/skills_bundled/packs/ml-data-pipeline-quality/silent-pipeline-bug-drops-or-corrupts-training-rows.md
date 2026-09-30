---
name: silent-pipeline-bug-drops-or-corrupts-training-rows
description: A training pipeline silently drops or corrupts a fraction of examples on every run, and the resulting model still looks plausible so nobody notices.
triggers: ["training data row count keeps changing", "model trained on incomplete dataset unnoticed", "join silently drops rows in pipeline", "pipeline succeeded but data is wrong"]
permissions: ["READ"]
---

## Symptom

A training pipeline runs to completion without errors and produces a
model that looks reasonable by every surface-level check, but the actual
row count feeding the model varies unexpectedly between runs, or is
quietly smaller than the known size of the source data -- and because
the model still trains and produces plausible-looking metrics, the
discrepancy goes unnoticed for weeks or months until someone happens to
compare row counts.

## Likely causes

- **An inner join silently drops unmatched rows** where a left join was
  intended -- a common bug when joining a labels table against a
  features table where not every labeled example yet has features
  computed, quietly shrinking the effective training set to only the
  overlap.
- **A deduplication or null-filtering step is more aggressive than
  intended**, dropping legitimate rows that merely have a null in a
  column not actually required for training, or that use a dedup key
  that isn't actually unique per intended example.
- **An upstream data source occasionally returns a partial result (a
  paginated API call that stops early, a distributed job that completes
  with some failed shards marked as "best effort" success) and the
  pipeline doesn't check row counts or completeness before proceeding**,
  so a partial extract is silently treated as a complete one.
- **A schema coercion step silently converts unparseable values to
  null/NaN and a downstream `dropna()` removes those rows** without
  logging how many were dropped or why, hiding a data quality problem
  inside what looks like normal missing-value handling.

## Diagnose

1. Instrument the pipeline to log row counts at every major stage
   (extract, each join, each filter, final training set) and compare
   consecutive stage counts against expectations -- a large unexplained
   drop between two adjacent stages localizes the bug immediately.
2. Compare the final training set's row count run-over-run across recent
   pipeline executions; unexplained variance (not attributable to actual
   new data volume) indicates non-determinism worth investigating, such
   as a race condition or an incomplete upstream dependency.
3. For every join in the pipeline, explicitly check the join type (inner
   vs. left/right/outer) against what's actually intended, and compute
   the count of unmatched rows on each side to quantify what an inner
   join would silently discard.
4. Check upstream data sources for any completeness/success signal
   (expected row count, checksum, "fully loaded" flag) and verify the
   pipeline actually asserts on that signal rather than only checking
   that the extract step didn't throw an exception.

## Fix

Add explicit row-count assertions and stage-by-stage data volume logging
throughout the pipeline, failing the run loudly (rather than silently
proceeding) when row counts drop below an expected threshold or vary
outside a normal range run-over-run. Replace joins with the join type
that actually matches intent, and where an inner join is genuinely
correct, log and periodically review the count of rows it excludes to
confirm that exclusion is expected rather than a growing silent loss.
Add explicit completeness checks against upstream sources (expected row
count, success flags per shard/partition) before the pipeline treats an
extract as usable.

## Pitfalls

Don't treat "the pipeline ran without throwing an exception" as
equivalent to "the pipeline produced correct data" -- silent data loss is
by definition invisible to error-based monitoring, and a pipeline that
only alerts on hard failures will never catch a join or filter that's
quietly discarding a growing fraction of examples over time.

## Verify

After adding row-count assertions, deliberately trigger the previously-
silent failure condition (a source with a known partial result, a join
key mismatch) in a test environment and confirm the pipeline now fails
loudly or logs a clear warning rather than proceeding silently. In
production, confirm stage-by-stage row counts are now visible in
monitoring/dashboards and set an alert threshold on unexpected count
drops between consecutive pipeline runs.
