---
name: dbt-seed-or-hardcoded-reference-data-drifts-from-source
description: A dbt seed file or hardcoded mapping used in transformation logic goes stale and silently misclassifies new data that the source system has since updated.
triggers: ["dbt seed out of date", "hardcoded mapping missing new values", "dbt case statement missing new category", "reference data drifted from source", "new value falls into other bucket unexpectedly"]
permissions: ["READ"]
---

## Symptom
A dbt model uses a seed file (a CSV loaded via `dbt seed`) or an inline
`CASE WHEN`/mapping table to classify or enrich data -- mapping country
codes to regions, product SKUs to categories, status codes to
human-readable labels. At some point, new values start appearing in the
source system (a new country launches, a new product category is added,
a new status code is introduced upstream) that aren't in the mapping, and
they silently fall into a default/`else`/`Unknown` bucket, or get
dropped entirely by a join, with no error or warning anywhere.

## Likely causes
1. **The mapping was built once, at the time the model was written,
   against the source system's values *at that moment*,** with no
   process for noticing when the source system adds new values later --
   the mapping isn't wrong, it's just incomplete for values that didn't
   exist yet when it was created.
2. **An inner join to a seed/mapping table silently excludes unmapped
   rows** rather than surfacing them, so the failure mode isn't a visibly
   wrong "Unknown" label but a quietly shrinking row count that's easy to
   miss unless someone is specifically comparing input and output volumes.
3. **A `CASE WHEN ... ELSE 'Other' END` pattern has a catch-all `ELSE`
   that was intended as a rare fallback but has become the default
   landing spot for an increasing share of real, current data,** and
   because it doesn't error, the growing "Other" bucket looks like normal
   output rather than a signal that the mapping needs updating.
4. **No test or monitor exists on the mapping's coverage** -- nothing
   checks "what fraction of rows landed in the fallback/unmapped
   category this run" over time, so a gradual increase from 1% to 15%
   "Other" happens invisibly.

## Diagnose
- Query the model's output for the distribution of the mapped/classified
  column and check the size of the fallback/`Unknown`/`Other` bucket as a
  percentage of total rows, then check whether that percentage has grown
  over recent history (this requires either historical snapshots or
  re-running against past dates) -- a rising trend is the direct signal.
- Compare the current distinct values in the source column against the
  distinct values present in the seed/mapping table (`SELECT DISTINCT
  source_column FROM source EXCEPT SELECT mapped_value FROM
  seed_mapping`) to get an exact list of unmapped values right now.
- If the join to the mapping table is an inner join, temporarily change
  it to a left join in an ad hoc query and compare row counts -- any
  increase directly quantifies rows being silently dropped by the
  original inner join.
- Check how the seed/mapping file is maintained: is it manually edited
  and PR'd only when someone notices a problem, or is there any
  recurring process (even manual) for reconciling it against the live
  source system's current value set?

## Fix
Make unmapped values loud instead of silent. Prefer a left join against
the mapping table (never an inner join, unless dropping unmapped rows is
truly the intended behavior) so new/unmapped source values still appear
in the output, explicitly labeled (e.g., `COALESCE(mapping.label,
'UNMAPPED: ' || source.raw_code)`) rather than silently excluded or
folded into a generic bucket that looks the same as a legitimate
category. Add a dbt test (a singular test, or a `dbt_utils.accepted_values`-
style test in reverse -- asserting the *fallback* bucket stays under a
threshold percentage) that fails the build when the unmapped/fallback
share of rows exceeds a small tolerance, turning silent drift into a
build failure that prompts someone to update the mapping. Where the
source system exposes its own reference/lookup data (an API, a
dimension table), consider sourcing the mapping from there directly
instead of a manually maintained seed file, so it can't drift out of
sync with the system it's describing at all.

## Pitfalls
- Setting the "unmapped share" test threshold to a number so loose it
  never actually fires (matching whatever the current drifted state
  already is, rather than a genuinely small tolerance) -- this adds the
  appearance of a safeguard without changing the actual failure mode.
- Fixing the immediate unmapped values by adding them to the seed file
  once, without addressing the underlying process gap -- the next new
  source value introduced will reproduce the exact same silent drift
  since nothing changed about how new values get noticed.
- Making unmapped values loud in the data (a visible `UNMAPPED: ` prefix)
  but not surfacing that anywhere a human will see it before it reaches
  a dashboard or report -- the value is louder in the raw data, but the
  audience who needs to act on it may never look at that raw data
  directly.

## Verify
Insert a synthetic new/unmapped value into a test copy of the source
data, run the model, and confirm both that the row appears in the output
(rather than being silently dropped) and that the coverage test fails as
designed, then confirm adding that value to the mapping file resolves
the test failure and the row now classifies correctly.
