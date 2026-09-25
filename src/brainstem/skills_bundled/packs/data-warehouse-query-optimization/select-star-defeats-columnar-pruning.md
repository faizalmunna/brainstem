---
name: select-star-defeats-columnar-pruning
description: A query uses SELECT star or otherwise scans an entire wide table when only a few columns are needed, losing the columnar warehouse's column-pruning cost and performance benefit.
triggers: ["select star slow", "query scanning all columns", "columnar pruning not happening", "why does this query cost so much for so few columns"]
permissions: ["READ"]
---

## Symptom
A query against a wide table (dozens to hundreds of columns) runs slower
and/or costs more (on byte-scanned billing like BigQuery, or in I/O time
on Redshift/Snowflake) than its actual logical output would suggest,
because it reads every column in the table even though the query's
`SELECT` list, filters, and joins only reference a handful of them.

## Likely causes
1. **Literal `SELECT *`** (or `SELECT t.*` in a join) used out of habit
   or during ad hoc exploration, then left unchanged when the query got
   promoted into a scheduled job or a BI dashboard's underlying query.
2. **An ORM or BI tool generates `SELECT *`-equivalent queries by
   default** (fetching a full row/model) even when the application or
   report only renders a few fields, because the abstraction layer
   doesn't know which columns the caller actually needs.
3. **A view or CTE wraps `SELECT *` internally**, and even though the
   outer query only selects a few columns, the engine can't push column
   pruning through the view/CTE boundary in some cases (particularly
   older engine versions or views involving certain window functions/
   UDFs that obscure column lineage).
4. **`SELECT *` used specifically to preserve forward-compatibility**
   with a table's evolving schema (so new columns automatically flow
   through), trading ongoing scan cost for a one-time convenience that
   was never revisited once the schema stabilized.

## Diagnose
- Grep the query text (or the BI tool's generated SQL, visible via query
  history) for `SELECT *` or `SELECT <alias>.*` patterns, especially in
  scheduled jobs and dashboard-backing queries with high execution
  frequency.
- BigQuery: use dry-run to compare bytes-scanned for the `SELECT *`
  version against a rewritten version selecting only the columns
  actually referenced downstream -- the difference is often dramatic on
  wide tables since BigQuery bills by columns scanned in a columnar
  table.
- Snowflake/Redshift: check the query profile/plan for the number of
  columns read per scan step, and compare against how many columns the
  final result set (or any filter/join predicate) actually needs.
- For views/CTEs, check whether column pruning is actually reaching the
  base table scan by inspecting the query plan's innermost scan node's
  column list, not just the outer query's `SELECT` clause.

## Fix
Replace `SELECT *` with an explicit column list matching exactly what
the query, its joins, and its filters need -- this is a mechanical,
low-risk rewrite for ad hoc and scheduled queries. For ORM- or BI-tool-
generated queries, configure the tool to request only the fields a given
report/page actually renders rather than a full-row fetch, where the
tool supports field-level selection. For views wrapping `SELECT *`,
rewrite the view itself to select explicit columns so pruning reaches
the base table regardless of how the view is subsequently queried.
Where forward-compatibility with new columns is genuinely needed,
document that tradeoff explicitly and revisit periodically, rather than
defaulting to `SELECT *` permanently on a table whose schema has
actually stabilized.

## Pitfalls
Blindly narrowing a `SELECT *` used inside a shared view without
checking every downstream consumer can silently break a consumer that
depended on a column not in the new explicit list -- inventory
downstream usage (via query history referencing the view, or a
dependency graph if the warehouse/orchestrator tracks lineage) before
narrowing a shared view's column list. Also, narrowing columns doesn't
help if the table's row-filtering predicate is the actual dominant cost
driver (e.g. an unpruned partition scan) -- column pruning and
partition/clustering pruning are separate, additive optimizations, and
fixing one doesn't substitute for the other.

## Verify
Re-run the rewritten query with dry-run/bytes-scanned estimation
(BigQuery) or check the query profile's scanned-column count
(Snowflake/Redshift) and confirm it reflects only the columns actually
selected. Confirm no downstream consumer broke by checking for new query
errors or missing-column complaints in the period immediately following
the change, particularly for any shared view that was modified.
