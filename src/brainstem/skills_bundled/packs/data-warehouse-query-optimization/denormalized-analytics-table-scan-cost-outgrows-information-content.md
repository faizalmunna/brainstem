---
name: denormalized-analytics-table-scan-cost-outgrows-information-content
description: A wide denormalized analytics table's storage and per-query scan cost grow much faster than its actual unique information content because of repeated duplicated columns per row.
triggers: ["wide table storage cost growing fast", "denormalized table too expensive to query", "flattened table scan cost too high", "analytics table has redundant duplicated data"]
permissions: ["READ"]
---

## Symptom
A wide, denormalized analytics table (built for BI convenience -- one row
per event or transaction with every related dimension attribute flattened
in) shows storage and query-scan cost growing noticeably faster than the
underlying business activity it represents, and queries against it that
only need a couple of columns are still expensive because of the table's
overall width and duplication.

## Likely causes
1. **Slowly-changing dimension attributes are repeated on every fact row**
   (e.g. a customer's full address and account-tier text repeated on
   every one of their thousand transactions) instead of being joined from
   a much smaller dimension table, so the same handful of unique values
   are stored and scanned millions of times over.
2. **The table was denormalized to avoid joins for BI tool simplicity**
   without accounting for the fact that modern warehouse engines handle
   joins against well-modeled dimension tables efficiently, so the
   join-avoidance tradeoff no longer pays for itself at current data
   volume.
3. **Historical snapshots are stored as full-row copies per change**
   (a new full row written every time any single attribute changes,
   commonly from a naive "insert new state daily" pattern) rather than
   only storing what changed, multiplying storage for attributes that
   rarely change.
4. **Nested/repeated fields (arrays, structs) intended for semi-structured
   convenience are flattened into many redundant scalar columns** during
   ingestion, losing the compact repeated-field representation the
   warehouse's native semi-structured support (e.g. BigQuery `STRUCT`/
   `ARRAY`, Snowflake `VARIANT`) would have offered.

## Diagnose
- Compare the table's total byte size (warehouse-reported storage) against
  a rough estimate of its actual unique information content -- e.g. count
  distinct values per wide dimension-like column
  (`SELECT approx_count_distinct(customer_address)`) versus total row
  count; a large gap indicates heavy duplication.
- Identify which columns are functionally dependent on a much smaller
  key (e.g. all customer-attribute columns depend only on `customer_id`,
  not on the transaction) -- those are candidates to move to a joined
  dimension table.
- Check query history for the table: what fraction of queries actually
  use the full row width vs. a small subset of columns -- if most
  queries touch 5 of 80 columns, the "avoid joins" premise the wide table
  was built on may no longer hold given columnar pruning.
- For snapshot-style tables, check whether consecutive snapshot rows for
  the same entity are mostly identical (diff a sample) -- a high
  similarity ratio confirms unnecessary full-row duplication versus a
  change-only or SCD Type 2 pattern.

## Fix
Split out slowly-changing, repeated attributes into a proper dimension
table joined at query time (or materialized into a narrower pre-joined
view only for the specific high-frequency query patterns that need it),
relying on the warehouse's join performance rather than pre-flattening
defensively. For historical tracking, use a change-tracking pattern (SCD
Type 2 with effective-date ranges, or a dedicated change-log table) so
storage scales with actual number of changes, not with a full-row copy
per snapshot interval. Where nested data was flattened into many sparse
scalar columns, consider the warehouse's native semi-structured column
type instead, which typically compresses repeated/sparse structure far
better than an equivalent wide flat schema.

## Pitfalls
Don't normalize reflexively back to a fully star-schema-pure model if the
actual dominant query pattern genuinely needs the pre-joined shape and
data volume is small enough that the duplication cost is negligible --
the fix is about cases where growth in storage/scan cost has become
disproportionate, not a blanket rule against denormalization, which is
often a legitimate and correct warehouse pattern at moderate scale.
Also, don't split out a dimension table without checking whether existing
downstream queries/dashboards depend on the flattened columns directly;
plan a migration path (a compatibility view) rather than breaking
consumers outright.

## Verify
After restructuring, compare total storage bytes and average bytes
scanned per representative query before and after, and confirm the
reduction is proportional to the duplication that was removed (not just
moved elsewhere). Re-run the dominant query patterns identified during
diagnosis against the new structure and confirm latency and cost are
equal or better despite the added join.
