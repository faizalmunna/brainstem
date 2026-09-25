---
name: postgres-slow-query-diagnosis
description: Systematically diagnose a slow Postgres query using EXPLAIN ANALYZE instead of guessing which index or rewrite will help.
triggers: ["slow postgres query", "query taking too long", "explain analyze", "postgres performance", "why is this query slow", "sequential scan slow"]
permissions: ["READ", "DATABASE"]
---

## Symptom
A specific query (or an endpoint backed by it) is noticeably slower than
expected, either consistently or only at larger data volumes/higher
concurrency than when it was first written and seemed fine.

## Likely causes
1. **A sequential scan on a large table** where an index on the filtered/
   joined column would let Postgres avoid scanning every row.
2. **An index exists but isn't used** -- often because the query applies
   a function to the indexed column (`WHERE lower(email) = ...` against a
   plain index on `email`), uses a type that requires an implicit cast, or
   the planner's statistics are stale enough that it chooses a sequential
   scan anyway.
3. **A join producing a much larger intermediate result than expected**
   (a fan-out join multiplying row counts before filtering), especially
   when filters that could reduce the join's input aren't applied early.
4. **N+1 query pattern at the application layer** -- not a single slow
   query, but many fast queries executed in a loop where one query with a
   join or `IN` clause would suffice (the general-purpose version of
   `graphql-n-plus-one`, applicable outside GraphQL too).
5. **Lock contention** -- the query itself is fast, but it's waiting on a
   lock held by a long-running transaction elsewhere.

## Diagnose
- Run `EXPLAIN (ANALYZE, BUFFERS) <query>` and read it from the innermost
  (deepest-indented) node outward: find the node with the largest actual
  time or row-count mismatch (`rows=` estimated vs. actual) -- that's
  usually the specific operation to fix, not the query as a whole.
- Check for `Seq Scan` on a large table where a `WHERE`/`JOIN` condition
  on that table's column would benefit from an index.
- Compare the planner's estimated row count against the actual row count
  in the `EXPLAIN ANALYZE` output -- a large mismatch suggests stale
  statistics (fix with `ANALYZE <table>`) rather than a missing index.
- For lock contention, check `pg_stat_activity` for other sessions in a
  long-running transaction (`state = 'active'` or `'idle in
  transaction'`) holding locks that overlap the slow query's target
  table.

## Fix
- Add an index on columns used in `WHERE`, `JOIN`, and `ORDER BY` clauses
  that currently trigger a sequential scan on a large table -- a
  composite index matching the actual filter+sort pattern, not just a
  single-column index, when the query filters/sorts on multiple columns
  together.
- For a function applied to the filtered column (`lower(email)`), create
  an expression index (`CREATE INDEX ON users (lower(email))`) matching
  exactly what the query applies, since a plain index on the raw column
  won't be used.
- Run `ANALYZE` on tables with stale statistics (or verify autovacuum's
  analyze is actually running -- see `postgres-vacuum-bloat`) so the
  planner's row estimates are accurate enough to choose good plans.
- Restructure joins to filter as early as possible (push `WHERE`
  conditions into subqueries/CTEs before joining, when the planner
  doesn't already do this automatically) to reduce intermediate result
  size.
- Replace an application-level N+1 query loop with a single query using
  a `JOIN` or `WHERE id = ANY($1)`/`IN (...)` batching the lookups.

## Pitfalls
- Adding an index speeds up reads but adds overhead to every write
  (insert/update/delete) that touches the indexed column, and consumes
  storage -- don't index every column defensively; index based on actual
  query patterns.
- A composite index's column order matters: an index on `(a, b)`
  efficiently serves queries filtering on `a` alone or `a AND b`, but not
  efficiently on `b` alone -- match the index column order to the
  queries that need to use it.
- Fixing symptoms shown by `EXPLAIN` without `ANALYZE` (which doesn't
  actually execute the query) can mislead, since the planner's *estimate*
  can differ significantly from real execution -- always use `EXPLAIN
  ANALYZE` (carefully, understanding it does execute the query) for
  genuine diagnosis, not just `EXPLAIN` alone.

## Verify
Re-run `EXPLAIN ANALYZE` after the fix and confirm the previously
expensive node (sequential scan, mismatched row estimate) is gone or
substantially cheaper, and measure actual query latency under realistic
data volume/concurrency, not just on a small local dataset.
