---
name: correlated-subquery-or-udf-forces-row-by-row-execution
description: A warehouse query runs far slower than its data volume suggests because a correlated subquery or per-row UDF forces row-by-row execution instead of set-based columnar processing.
triggers: ["correlated subquery slow", "udf making query slow", "query slower than expected for row count", "why is this scalar subquery so expensive", "python udf snowflake slow"]
permissions: ["READ"]
---

## Symptom
A query returns a result set that seems small enough to be fast, but
takes far longer than comparable queries over similar data volumes --
the query profile shows a disproportionate amount of time in a single
operator rather than spread across scan/join/aggregate steps the way a
typical set-based query would show.

## Likely causes
1. **A correlated subquery re-executes once per outer row** (a scalar
   subquery in the `SELECT` list, or an `EXISTS`/`IN` subquery referencing
   an outer-query column) instead of being rewritten as a join or window
   function, so cost scales with outer row count times subquery cost
   rather than being computed set-at-a-time.
2. **A scalar or row-level UDF (especially a Python/JavaScript UDF on
   Snowflake, or a JS UDF on BigQuery) is applied per row** where a
   built-in vectorized SQL function or a vectorized/pandas UDF variant
   would process the same logic in batches, and row-by-row UDF
   invocation overhead dominates runtime on large tables.
3. **A window function or aggregation is computed over an unnecessarily
   wide partition** (e.g. `PARTITION BY` a column with very low
   cardinality, or omitted entirely when it should narrow the window),
   forcing the engine to hold and process much larger row sets per
   window than the logical calculation requires.
4. **A recursive CTE or iterative procedural loop (stored procedure logic
   looping over rows) reimplements what could be a single set-based
   query**, common when logic is ported from a row-oriented application
   language without rethinking it in SQL terms.

## Diagnose
- Check the query profile for an operator with disproportionate time or
  row-processing count relative to its position in the plan (Snowflake
  query profile shows time per operator node; BigQuery's execution
  details show stage-level time; Redshift's `SVL_QUERY_SUMMARY` shows
  per-step timing).
- Search the query text for a subquery inside `SELECT`, `WHERE`, or
  `HAVING` that references a column from the outer query (the defining
  trait of a correlated subquery) -- these are visually identifiable by
  the inner query needing the outer alias to resolve.
- Check for UDF usage (`CREATE FUNCTION`/`CREATE PROCEDURE` calls in the
  query) and check whether the warehouse offers a vectorized/batch UDF
  variant (e.g. Snowflake Python UDFs support a vectorized/pandas batch
  API) that isn't being used.
- For window functions, check the `PARTITION BY` clause's column
  cardinality against the table's total row count -- a very small number
  of partitions relative to row count means each partition (and thus each
  window computation) handles a very large row set.

## Fix
Rewrite correlated subqueries as joins (often a `LEFT JOIN` plus
aggregation) or window functions, which let the engine process the
computation set-at-a-time using its normal columnar/vectorized execution
path instead of a nested per-row loop. Replace row-by-row scalar UDFs
with built-in SQL functions where equivalent logic exists, or switch to
the warehouse's vectorized/batch UDF interface when custom logic is
genuinely required, since batch UDFs amortize invocation overhead across
many rows instead of paying it per row. Narrow window function
partitions to match the actual logical grouping needed. Reimplement
procedural row-looping logic (stored procedures iterating cursors) as a
single set-based SQL statement wherever the logic doesn't have a genuine
sequential dependency between rows.

## Pitfalls
Not every subquery that looks correlated needs rewriting -- some
warehouse optimizers already de-correlate simple, provably-equivalent
correlated subqueries into joins automatically; verify via the query
plan that the engine is actually executing it row-by-row before
investing in a rewrite. Also, converting a subquery to a join can change
result semantics subtly around `NULL` handling and duplicate rows (an
`EXISTS` subquery and its join-based rewrite aren't always exactly
equivalent for rows with `NULL` join keys or one-to-many relationships)
-- validate output row counts and values match, not just that the query
runs faster.

## Verify
Compare the query profile's operator-level time breakdown before and
after the rewrite and confirm the disproportionate operator is gone or
now proportionate to data volume. Run both the original and rewritten
query against the same data and diff the result sets (row counts and
values) to confirm the rewrite preserved correct semantics, not just
improved speed.
