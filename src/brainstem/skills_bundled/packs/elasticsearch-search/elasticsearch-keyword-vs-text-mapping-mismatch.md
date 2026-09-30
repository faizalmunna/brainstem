---
name: elasticsearch-keyword-vs-text-mapping-mismatch
description: A numeric-looking or categorical field was dynamically mapped as analyzed text (or vice versa) so aggregations, sorting, or exact-match filters fail or return wrong results.
triggers: ["Fielddata is disabled on text fields", "can't sort on this field in elasticsearch", "aggregation returns fragmented terms", "terms aggregation splitting on spaces", "exact match not working on keyword field", "why is my status field an object"]
permissions: ["READ"]
---

## Symptom
A terms aggregation on a `status` or `sku` field returns oddly fragmented
buckets (each word of a multi-word value as its own bucket), or a query
tries to sort/aggregate on a field and Elasticsearch returns
`Fielddata is disabled on text fields by default`, or an exact-match
filter (`term` query) on what looks like a simple code/ID field silently
matches nothing even though the value is clearly present in `_source`.

## Likely causes
1. **Dynamic mapping guessed wrong at first-document time.** Elasticsearch's
   dynamic mapping inspects the first document that introduces a field: a
   string value like `"Order-4821"` or `"draft"` gets mapped as `text`
   (analyzed, tokenized) unless it looks like a date or number, and once
   that mapping is set for the index, every later document is forced into
   it regardless of whether later values look more like an identifier.
2. **The field is genuinely mixed-use** (needs both full-text search and
   exact aggregation/sorting) but was mapped as a single type instead of
   using the `fields` multi-field feature to index it both ways.
3. **A numeric-looking identifier was mapped as `long`/`integer`** instead
   of `keyword` because it happened to be all-digits in the first document
   (e.g. a zero-padded account number `"00042"` loses its leading zeros
   once coerced to a number, and can never do prefix/wildcard matching).
4. **`_source` shows the "right" value but the query targets the wrong
   sub-field** -- the mapping is actually correct (`text` field with a
   `.keyword` multi-field), but the query or aggregation is pointed at the
   base field name instead of `fieldname.keyword`.

## Diagnose
- Run `GET /<index>/_mapping/field/<fieldname>` and read the actual type
  Elasticsearch chose -- don't assume from the field name or from what
  `_source` displays, since `_source` always shows the original JSON
  regardless of how the field was indexed.
- If the type is `text`, check whether a `.keyword` multi-field exists
  under `fields` in the mapping output; if it doesn't, no exact-match or
  aggregation path exists for that field at all without reindexing.
- Reproduce the failing aggregation/sort/term-query against
  `<fieldname>.keyword` explicitly to confirm whether the fix is "use the
  keyword sub-field" (already exists) versus "no keyword mapping exists"
  (needs a mapping change and reindex).
- For a numeric field that should have been a string identifier, check
  `GET /<index>/_search` for a document with a leading-zero or
  non-numeric variant of the same conceptual ID -- if such values exist
  elsewhere in the source system, the numeric mapping has already caused
  silent data loss on ingestion for those documents.

## Fix
- If a `.keyword` multi-field already exists on a `text` field, redirect
  the aggregation/sort/exact-match query to `<fieldname>.keyword` --
  this requires no reindex, only a query-side change.
- If no `.keyword` multi-field exists, update the mapping template (index
  template or component template) to add one going forward, and reindex
  existing data into a new index built from the corrected mapping (see
  the alias-based reindex pattern in
  `elasticsearch-zero-downtime-reindex-for-mapping-fix`) -- mappings for
  an existing field on an existing index cannot be changed in place.
- For fields that are identifiers, codes, statuses, or enum-like values
  (not intended for free-text search), map them explicitly as `keyword`
  from the start via an index template rather than relying on dynamic
  mapping to guess correctly -- explicit mapping removes the ambiguity
  dynamic mapping is inherently exposed to.
- For fields needing both full-text relevance search and exact
  aggregation (e.g. a product `name` field), map as `text` with a
  `keyword` multi-field (`"fields": {"keyword": {"type": "keyword",
  "ignore_above": 256}}`) so both access patterns are supported from one
  field.

## Pitfalls
- Setting `ignore_above` too low on a `keyword` multi-field silently drops
  indexing of that sub-field for any value longer than the limit (the
  document is still indexed, but that field becomes unsearchable/
  unaggregatable for long values) -- size it to the actual expected
  value length, not the default 256 blindly.
- Switching a numeric field to `keyword` to "fix" this changes sort order
  semantics from numeric to lexicographic (`"10"` sorts before `"9"`) --
  confirm downstream sort/range-query behavior is re-verified, not just
  aggregation behavior.
- Disabling dynamic mapping entirely (`"dynamic": "strict"`) as a
  defensive fix without also shipping explicit mappings for every field
  that will ever appear causes document rejection at index time instead
  of silent mis-mapping -- safer than the original bug, but only if
  paired with a real mapping template, not applied alone.

## Verify
Run `GET /<index>/_mapping/field/<fieldname>` and confirm the field (or
its `.keyword` multi-field) has the intended type, then re-run the
originally failing aggregation or term query and confirm bucket counts
match the expected distinct values (e.g. `cardinality` aggregation count
matches the known number of distinct statuses/SKUs in the source system).
