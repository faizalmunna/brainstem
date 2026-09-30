---
name: dynamodb-single-table-design-overloaded-key-query-mismatch
description: A single-table DynamoDB design needs a new access pattern that its overloaded partition and sort key scheme cannot serve without a full table scan or migration.
triggers: ["dynamodb single table design new access pattern doesn't fit", "dynamodb overloaded partition key PK SK generic names", "can't query dynamodb single table for new feature", "dynamodb single table design painted into a corner", "how to add access pattern to existing dynamodb single table"]
permissions: ["READ"]
---

## Symptom
A team adopted single-table design with generic overloaded key names
(`PK`/`SK`, entity-type prefixes like `USER#`, `ORDER#`) to serve a
specific, known set of access patterns efficiently. Later, a new feature
needs a query that the existing key structure doesn't support -- "get all
orders across all customers placed in the last hour," "find users by
partial email match," "list items sorted by a field that isn't the
current sort key" -- and the team's options all look bad: a full `Scan`
with filtering (slow, expensive, see the Scan-vs-Query skill in this
pack), a new GSI bolted on reactively without the upfront design
discipline the rest of the table had, or a realization that the access
pattern simply can't be served without restructuring existing item keys.

## Likely causes
1. **Single-table design was adopted for its efficiency benefits (fewer
   round trips, related entities co-located) without first enumerating
   the full set of access patterns the application would ever need** --
   the methodology explicitly requires access-pattern-first design (list
   every query the app needs, then design keys to serve all of them
   before creating the table), and skipping that step is the single most
   common root cause of hitting a wall later.
2. **A genuinely new, unanticipated feature requirement emerged after
   launch** that no amount of upfront design could have predicted (a
   product pivot, a new admin/reporting need, a new integration) -- not
   every case is a process failure; sometimes requirements legitimately
   change, and the key design needs deliberate evolution, not blame.
3. **The overloaded key's generic attribute names (`PK`, `SK`, `GSI1PK`)
   were never documented with the entity-type mapping that gives them
   meaning**, so even where the original design *could* serve the new
   pattern with a smart composite key trick, nobody currently on the team
   can reconstruct the original design's intent well enough to extend it
   correctly without risking breaking existing access patterns.
4. **Existing items were written without the attributes a new access
   pattern needs as key material** (e.g. a new GSI needs a `status`
   attribute as its key, but historical items were written before that
   attribute existed or was populated), so even after adding the right
   index, a backfill is required before the new pattern works for
   pre-existing data.

## Diagnose
- Locate (or reconstruct, if undocumented) the table's access-pattern-to-key
  mapping -- for every existing GSI and the base table, what entity
  types use which key prefixes, and which specific application queries
  map to which index. This is prerequisite work before evaluating whether
  the new pattern fits.
- Check whether the new access pattern's required filter/sort attribute
  already exists on the relevant items and is populated on all of them
  (not just newly created ones) -- `Scan` a sample or check item counts
  via a temporary index to confirm coverage.
- Evaluate whether the new pattern can be served by an **additional GSI**
  using existing or lightly-adjusted attributes (the common, low-risk
  case) versus requiring a **new overloaded key format on existing items**
  (higher-risk, needs a backfill/migration of live data) versus being
  fundamentally something DynamoDB's key-value/query model doesn't fit
  well (candidate for a different store or an OpenSearch/Elasticsearch
  side-index for the specific pattern, e.g. free-text or partial-match
  search).
- Check current table traffic and size to scope migration risk -- adding
  a GSI to a large, high-traffic table triggers a backfill that consumes
  additional write capacity and takes time proportional to table size,
  which needs to be planned for, not treated as an instant change.

## Fix
For patterns servable by a new GSI on existing or newly-added attributes,
add the GSI following the same discipline as original design: confirm its
key cardinality won't create a new hot-partition problem (see this pack's
hot-partition and GSI-skew skills), choose minimal projection for what
the new pattern actually reads (see the GSI over-projection skill), and
backfill the key attribute onto existing items if it wasn't previously
populated -- typically via a scripted batch update or, for large tables,
a Streams-driven or EMR/Glue-based backfill job rather than a blocking
in-place migration. For patterns that genuinely don't fit DynamoDB's
model (full-text search, complex ad-hoc analytical queries, arbitrary
multi-attribute filtering), don't force it -- stream table changes (via
DynamoDB Streams) into a purpose-built secondary system (OpenSearch for
search, a data warehouse for analytics) rather than contorting the
primary table's key design to serve a fundamentally different access
shape. Going forward, document the access-pattern-to-key mapping
explicitly (an ER diagram or table alongside the schema) specifically so
future additions can be evaluated against it instead of guessed at.

## Pitfalls
Reactively bolting on a `Scan`-with-filter as a quick fix for an
unsupported pattern (rather than a proper GSI or external index) is the
single most common way single-table designs quietly degrade into
expensive, slow tables over time -- each such shortcut is individually
justifiable under deadline pressure but compounds. Also, when a backfill
is needed to populate a new key attribute on existing items, running it
as an unthrottled batch job against a live production table can itself
cause the write-capacity throttling problems documented elsewhere in this
pack -- backfills need the same rate-limiting/pacing discipline as any
other bulk write workload.

## Verify
Confirm the new access pattern is served by a `Query` (not a `Scan`) with
`ScannedCount` matching `Count` in responses, confirm the backfill (if
one was needed) completed for 100% of eligible existing items (spot-check
via a count query against the new index versus total expected matching
items in the base table), and confirm existing access patterns' latency
and consumed capacity are unchanged after the new GSI/backfill, ruling
out regression from the change.
