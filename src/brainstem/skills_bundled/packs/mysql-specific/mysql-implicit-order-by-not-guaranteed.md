---
name: mysql-implicit-order-by-not-guaranteed
description: Query results silently change row order after a MySQL upgrade, index change, or optimizer plan shift because no explicit ORDER BY was ever specified.
triggers: ["query results in different order after upgrade", "rows out of order without order by", "pagination results shifted after index change", "mysql result order changed silently", "downstream consumer got wrong order from query"]
permissions: ["READ"]
---

## Symptom
Rows come back in a different order than before -- after a MySQL version
upgrade, an index added or dropped, a query rewritten slightly, or even
just after enough data accumulated to change the optimizer's chosen plan
-- even though no `ORDER BY` clause exists in the query. A downstream
consumer that depended on the old ordering (pagination, a "first N"
selection, a diff/comparison against a previous run, a UI list) breaks
or produces subtly wrong output, often not caught until well after the
change that caused it.

## Likely causes
1. **The query has no `ORDER BY` at all**, and the application (or a
   human) observed a consistent order during development or in early
   production and implicitly assumed that order was guaranteed, when it
   was actually just an artifact of the storage engine's current access
   path (e.g., returning rows in primary-key/clustering-index order for
   a full scan) -- which MySQL never promises to preserve.
2. **An index was added, dropped, or changed**, causing the optimizer to
   choose a different access path (index scan vs. table scan, or a
   different index) for the same query, which changes the row order that
   "happens" to result, with no logic change and no explicit ordering
   anywhere.
3. **A version upgrade changed optimizer behavior** -- cost-based
   optimizer changes between major MySQL/MariaDB versions can pick
   different execution plans for the same query and schema, so identical
   SQL against identical data returns rows in a different order purely
   because the optimizer's internal decision changed.
4. **`GROUP BY` was relied on for ordering** -- older MySQL versions
   implicitly sorted `GROUP BY` results in group-key order in many cases,
   which some queries came to depend on without an explicit `ORDER BY`;
   this implicit sort is not a documented guarantee and newer
   versions/plans can produce unsorted grouped output.
5. **Pagination via `LIMIT`/`OFFSET` without a stable, unique sort key**
   -- even with an `ORDER BY` present, if the sort column has duplicate
   values and isn't paired with a tiebreaker (like the primary key), rows
   with equal sort-key values can be returned in a different relative
   order across pages or across runs, producing skipped or duplicated
   rows in paginated output.

## Diagnose
- Grep the query (and any ORM-generated SQL, via query logging) for the
  absence of `ORDER BY` where a specific order is being assumed by the
  application or by a downstream consumer.
- If `ORDER BY` is present, check whether the sort column(s) alone
  uniquely determine order -- run `EXPLAIN` and check for duplicate
  values in the sort column across the affected rows; a sort key with
  ties combined with `LIMIT`/`OFFSET` is enough to explain inconsistent
  paging even with an explicit `ORDER BY`.
- Run `EXPLAIN` (or `EXPLAIN ANALYZE`) on the query before and after the
  suspected change (index add/drop, version upgrade) and compare the
  chosen access path -- a changed `type`/`key`/`Extra` column
  (e.g., `Using filesort` appearing or disappearing, or a different index
  in `key`) confirms the optimizer's plan changed, which is consistent
  with an order change even though results are still "correct" per SQL
  semantics.
- Check the MySQL/MariaDB changelog for the version jump in question for
  optimizer or `GROUP BY` ordering behavior changes -- MySQL 8.0
  explicitly documented that `GROUP BY` no longer implies any particular
  sort order, which is a common trigger for this exact symptom during
  5.7-to-8.0 upgrades.

## Fix
- Add an explicit `ORDER BY` to every query whose result order the
  application or a downstream consumer depends on, treating "no
  `ORDER BY`" as meaning "order is unspecified and may change at any
  time," per the SQL standard and MySQL's own documentation, rather than
  as "order happens to be stable."
- For paginated or "first N" queries, make the sort key unique by
  appending a tiebreaker column (typically the primary key):
  `ORDER BY created_at, id LIMIT ... OFFSET ...` so rows with identical
  `created_at` values still have a fully deterministic, repeatable order
  across pages and across query re-runs.
- Where `GROUP BY` output order matters, add an explicit `ORDER BY`
  rather than relying on any incidental grouping order -- this is
  required for correctness on MySQL 8.0+ and is good practice on any
  version.

## Pitfalls
- Adding `ORDER BY` on a large table without a supporting index
  introduces a `filesort` that can meaningfully slow the query -- check
  `EXPLAIN` for `Using filesort` after adding the clause and add a
  covering/composite index if the query is hot, rather than accepting a
  silent performance regression as the cost of correctness.
- Fixing only the specific query that broke, without auditing sibling
  queries built the same way (same ORM pattern, same missing tiebreaker),
  leaves the same class of bug to resurface on the next optimizer or
  index change.
- Assuming a single-column `ORDER BY` is sufficient for pagination
  stability without checking for duplicate values in that column is a
  common half-fix that still produces occasional skipped/duplicated rows
  under real data distributions.

## Verify
Run the query with `EXPLAIN` and confirm the plan no longer depends on
an unspecified access-path order for correctness (an explicit
`ORDER BY` is present and, for paginated queries, includes a unique
tiebreaker); then re-run the query multiple times and across a schema
change or index rebuild in a staging environment and confirm row order
is identical every time, including for rows that share the same primary
sort-key value.
