---
name: missing-schema-validation-lets-upstream-change-corrupt-training-data
description: A training run silently ingests corrupted data because no schema or data-contract validation exists to catch an upstream column rename, type change, or unit change.
triggers: ["training run used wrong data after upstream change", "renamed column broke pipeline silently", "no schema validation on training data", "unit change corrupted model features"]
permissions: ["READ"]
---

## Symptom

A training run completes normally and produces a model, but the model's
behavior or performance shifts unexpectedly after a routine, unrelated
change somewhere upstream (a source table gets a column renamed, an
API's response format changes, a unit of measurement changes) -- there
is no pipeline failure, no exception, no obvious alert, and the
connection between the upstream change and the model regression is only
discovered later through manual investigation, if at all.

## Likely causes

- **A column was renamed, reordered, or dropped upstream, and the
  pipeline reads by position or uses a permissive parser that fills the
  missing/renamed field with null or a default rather than failing**, so
  the feature silently becomes all-null or all-default without the
  pipeline noticing anything is wrong.
- **A unit or encoding changed upstream** (a currency field switches from
  cents to dollars, a timestamp switches from local time to UTC, a
  categorical field's encoding changes from strings to integer codes)
  without any corresponding pipeline update, so every downstream feature
  derived from that field becomes systematically wrong while remaining
  syntactically valid.
- **No data contract or schema definition exists between the upstream
  data producer and the training pipeline**, so there's no shared,
  enforced agreement about what columns, types, and value ranges the
  pipeline can expect, and any producer-side change is a silent breaking
  change from the pipeline's perspective by default.
- **Type coercion during ingestion is overly permissive** (e.g., a
  strongly-typed schema isn't enforced and everything is read as a
  generic string or object type), so a type change that would otherwise
  cause an obvious parsing failure instead passes through and only
  causes a downstream numerical or logical error much later in the
  pipeline.

## Diagnose

1. Check whether the pipeline validates incoming data against an explicit
   schema (column names, types, nullability, expected value
   ranges/categories) before proceeding, or whether it simply reads
   whatever arrives and proceeds optimistically.
2. Review recent changes to the upstream data source (schema migration
   logs, API changelog, source table DDL history) around the date the
   model's behavior shifted, looking specifically for renames, type
   changes, or unit changes.
3. Compare summary statistics (null rate, min/max, cardinality, mean) for
   each feature between the suspect training run and a known-good prior
   run -- a sudden shift in a specific column's null rate or value range
   points directly at the affected field.
4. Check whether the training pipeline logs or persists a copy of the raw
   schema it ingested for each run, which would let this comparison be
   done retroactively rather than requiring the bug to still be
   reproducible.

## Fix

Add an explicit schema validation step at data ingestion (a tool like
Great Expectations, Pandera, or a hand-rolled schema check) that asserts
expected column names, types, nullability, and reasonable value
ranges/categories before the pipeline proceeds, and fails the run loudly
with a specific, actionable error when validation fails rather than
silently coercing or nulling out unexpected data. Establish an explicit
data contract with upstream producers (a versioned schema definition
both sides agree to) so schema changes become a coordinated, visible
event rather than a silent one, and add automated schema-diffing between
consecutive runs to catch drift even in fields validation doesn't
explicitly check.

## Pitfalls

Don't treat schema validation as a one-time setup task -- a validation
schema that's written once and never updated becomes stale as the
pipeline legitimately evolves, leading teams to either disable checks
that now "always fail" on legitimate changes, or to widen tolerances so
much that the validation no longer catches anything meaningful.

## Verify

Deliberately introduce a simulated upstream change (rename a column,
change a unit) in a test/staging environment and confirm the schema
validation step catches it and fails the pipeline with a clear,
specific error message identifying the affected field. Confirm the
validation step is wired into the actual production training pipeline
(not just a standalone script) and that a validation failure blocks the
training run from proceeding rather than only logging a warning.
