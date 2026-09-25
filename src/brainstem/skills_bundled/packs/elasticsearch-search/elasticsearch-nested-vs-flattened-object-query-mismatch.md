---
name: elasticsearch-nested-vs-flattened-object-query-mismatch
description: Queries filtering on multiple fields of an array of objects incorrectly match across unrelated array entries because the field was mapped as plain object instead of nested.
triggers: ["array of objects query matching wrong combination", "nested query elasticsearch cross matching", "why does my filter match the wrong item in the array", "object type flattening arrays elasticsearch", "nested mapping vs object mapping"]
permissions: ["READ"]
---

## Symptom
A document containing an array of sub-objects (e.g.
`"variants": [{"color": "red", "size": "S"}, {"color": "blue", "size":
"L"}]`) matches a compound query intended to find "red AND size S"
even when the actual document only has "red, size L" and "blue, size S"
-- the query is matching color from one array entry and size from a
different entry, not from the same logical object.

## Likely causes
1. **The field is mapped as the default `object` type** (or dynamically
   mapped without an explicit `nested` type), which internally flattens
   an array of objects into separate arrays per leaf field
   (`variants.color: ["red", "blue"]`, `variants.size: ["S", "L"]`),
   permanently losing the association between which color went with
   which size for query purposes.
2. **A `nested` mapping exists, but the query uses a plain `bool`/`term`
   query against the nested field paths directly** instead of wrapping
   the condition in a `nested` query -- `nested` fields are stored as
   separate hidden Lucene documents internally, and only a `nested` query
   (with the correct `path`) actually queries within a single one of
   those inner documents; a non-`nested` query against the same field
   paths falls back to the flattened, cross-matching behavior.
3. **Aggregations on nested fields omit the required `nested` aggregation
   wrapper** (and `reverse_nested` when aggregating back up to the parent
   document level), producing bucket counts that don't correspond to
   real per-parent-document semantics.
4. **The array-of-objects field was mapped as `nested` after data already
   existed under the default `object` mapping**, and the index wasn't
   reindexed, so the mapping now says `nested` but the underlying segment
   data for existing documents wasn't restructured into the separate
   inner-document form `nested` queries expect.

## Diagnose
- Run `GET /<index>/_mapping/field/<fieldname>` and confirm the array
  field's actual mapped type -- `object` (or absent/dynamic) versus
  explicit `nested`.
- Reproduce the cross-matching bug with a minimal test document
  containing two array entries with deliberately distinguishable,
  non-overlapping values in each sub-field, and confirm the query
  matches when it shouldn't -- this concretely proves flattening rather
  than requiring inference from production data.
- If the mapping is already `nested`, check the actual query structure
  for a `nested` query wrapper with the correct `path` parameter --
  a `bool`/`term` query referencing `variants.color` without being
  inside a `nested` query block is the direct cause even with a correct
  mapping.
- For aggregation-side symptoms, check whether the aggregation is wrapped
  in a `nested` aggregation with matching `path`, and whether a
  `reverse_nested` aggregation is used wherever the result needs to
  reflect parent-document-level counts rather than inner-object-level
  counts.

## Fix
- Map the array-of-objects field explicitly as `"type": "nested"` in the
  index template/mapping, understanding the tradeoff: `nested` correctly
  preserves per-object field association but each nested object is
  indexed as a separate hidden Lucene document, so a field with very
  many array entries per document (thousands) has real indexing/memory
  cost implications worth sizing against actual data before adopting.
- Rewrite queries against nested fields to use the `nested` query type
  with the correct `path`, containing the compound condition (`bool`
  with multiple `must`/`term` clauses on the sub-fields) *inside* the
  `nested` query so all conditions are evaluated against the same inner
  object.
- Wrap aggregations on nested fields in a `nested` aggregation (matching
  `path`), and add `reverse_nested` where the result needs to count
  distinct parent documents rather than distinct inner objects.
- If the mapping was changed to `nested` after data already existed under
  `object`, reindex (see `elasticsearch-zero-downtime-reindex-for-
  mapping-fix`) so existing documents are actually restructured into the
  nested inner-document form -- changing the mapping alone doesn't
  retroactively restructure already-indexed data.

## Pitfalls
- Reaching for `nested` mapping by default for every array-of-objects
  field without checking whether queries actually need cross-field
  per-object correlation adds real indexing and query cost (nested
  queries are measurably more expensive than flat term queries) for
  cases that might not have needed it -- use `nested` when the
  correlation is actually required, not defensively everywhere.
- Forgetting `inner_hits` when a `nested` query needs to also report
  *which* specific inner object(s) matched (not just that the parent
  document matched) leads to a follow-up "which variant matched" question
  the initial query can't answer without a second lookup.
- Mixing a `nested` field's parent-level fields and nested-level fields
  in the same top-level `bool` query without realizing the nested
  portion must be inside its own `nested` query block is a common
  incremental-query-building mistake once the base nested query is
  already correct.

## Verify
Re-run the minimal reproduction case (the two-entry test document with
non-overlapping sub-field values) against the corrected mapping and
query, and confirm it no longer cross-matches; for aggregation fixes,
confirm bucket counts against a manually counted small sample match the
`reverse_nested`-corrected aggregation output.
