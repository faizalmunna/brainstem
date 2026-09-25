---
name: postgres-json-column-tradeoffs
description: Decide when a JSONB column is the right choice in Postgres versus proper relational columns/tables, and fix performance problems from JSONB used past that point.
triggers: ["jsonb vs columns", "should i use jsonb", "jsonb query slow", "json column performance postgres", "schemaless postgres design"]
permissions: ["READ", "DATABASE"]
---

## Symptom
Either a design question (whether to model a piece of data as a JSONB
column versus normalized relational columns/tables), or a performance/
correctness problem from JSONB already used past where it fits well:
slow queries filtering into deeply nested JSON, difficulty enforcing data
integrity on fields that should be required/typed, or queries that can't
use an index effectively.

## Likely causes (when diagnosing an existing JSONB problem)
1. **Filtering/sorting on a JSONB field without a matching index** --
   Postgres can index JSONB (GIN indexes for containment queries,
   expression indexes for specific paths), but a query into JSONB with no
   supporting index falls back to scanning and parsing JSON for every
   row.
2. **JSONB used for data that's actually always present and has a fixed
   shape** (e.g. `{"email": ..., "name": ...}` on every row, always) --
   this gets none of JSONB's genuine benefit (flexible/sparse/variable
   shape) while losing type checking, `NOT NULL`/foreign-key constraints,
   and straightforward indexing that plain columns would give for free.
3. **Business logic validating JSONB structure only in application code**,
   with no database-level constraint, so malformed/inconsistent data can
   still be written directly (migrations, scripts, a different service)
   and go undetected until it breaks something downstream.
4. **Deeply nested JSONB queried frequently by a specific inner field**,
   turning what's conceptually a relational query into repeated JSON path
   traversal, which is both slower and harder to express than a normal
   `WHERE`/`JOIN` would be.

## Diagnose
- For a design decision, ask: is this data's shape genuinely
  variable/sparse across rows (good fit for JSONB), or does every row
  have the same fields with the same types (better fit as real columns)?
  Will queries need to filter/sort/join on specific fields inside it
  frequently (favors real columns or at least an indexed expression), or
  is it mostly stored and retrieved whole (JSONB is fine)?
- For a performance problem, check `EXPLAIN ANALYZE` on the query
  filtering into JSONB and confirm whether it's doing a sequential
  scan/JSON parse per row versus using a GIN or expression index.
- Check whether critical fields inside the JSONB are ever missing/
  malformed in practice (a sign integrity should be enforced, not just
  hoped for).

## Fix
- For data with a fixed, known shape present on every row, use real
  typed columns (with `NOT NULL`, foreign keys, and check constraints as
  appropriate) rather than JSONB -- this gives type safety, straightforward
  indexing, and query simplicity for free.
- For genuinely variable/sparse data (a flexible "extra attributes" bag,
  event payloads with a per-event-type shape), JSONB is the right choice
  -- add a GIN index for containment (`@>`) queries, or an expression
  index on a specific frequently-queried path
  (`CREATE INDEX ON t ((data->>'status'))`) if one particular field
  inside the JSON is queried often.
- For a field that started as JSONB but turned out to be always-present
  and frequently queried, promote it to a real column (a migration that
  extracts it out, following the safe zero-downtime pattern in
  `database-migration-zero-downtime`) rather than continuing to
  work around JSON-query limitations indefinitely.
- Add database-level `CHECK` constraints validating JSONB structure for
  required sub-fields where integrity actually matters, rather than
  relying solely on application-layer validation that other writers
  (migrations, other services) can bypass.

## Pitfalls
- Adding a GIN index on an entire JSONB column when only one specific
  path is ever queried is heavier (index size, write overhead) than a
  targeted expression index on just that path -- match the index to the
  actual query pattern.
- "We might need flexibility later" is a weak justification for JSONB on
  data that's fixed-shape today -- Postgres migrations for adding real
  columns are cheap and safe when done incrementally (see
  `database-migration-zero-downtime`); the flexibility argument is
  usually not worth the ongoing cost of losing type safety and easy
  indexing now.

## Verify
For a query performance fix, confirm via `EXPLAIN ANALYZE` that the JSONB
query now uses the new index (a `Bitmap Index Scan`/`Index Scan` on the
GIN or expression index, not a `Seq Scan`); for a data-integrity fix,
attempt to insert a row that violates the new constraint and confirm the
database rejects it rather than only the application layer catching it.
