---
name: postgres-full-text-search-limits
description: Decide whether Postgres's built-in full-text search is sufficient or whether a dedicated search engine is actually needed, and fix common tsvector/tsquery mistakes.
triggers: ["postgres full text search", "when to use elasticsearch", "tsvector tsquery", "search feature slow postgres", "postgres search not finding results"]
permissions: ["READ", "DATABASE"]
---

## Symptom
Either a design question (should search be built on Postgres's `tsvector`/
`tsquery` or a dedicated engine like Elasticsearch/OpenSearch/Meilisearch),
or a concrete bug: Postgres full-text search not finding results a user
expects, ranking results in a confusing order, or the search feature
degrading as data volume grows.

## Likely causes (for a specific bug)
1. **No GIN index on the `tsvector` column**, so every search does a
   sequential scan and re-computation of the text-search vector for every
   row, which works fine on small tables and degrades sharply as the
   table grows.
2. **Search terms not matching due to language/stemming configuration
   mismatch** -- the `tsvector` was generated with one text-search
   configuration (e.g. `english`, which stems and removes stop words) but
   the query expects literal substring or a different language's
   stemming behavior.
3. **Multi-word/prefix search expectations not met** by a naive
   `plainto_tsquery`, which doesn't support prefix matching
   (`gree` matching `green`) the way users often expect from a search box.
4. **Ranking (`ts_rank`) not matching user expectations** because it's
   applied with default weighting across all fields uniformly, when
   users would expect a title match to rank above a body-text match, for
   example.

## Diagnose
- Check whether a GIN index exists on the `tsvector` expression/column
  used by the search query -- `EXPLAIN ANALYZE` will show a sequential
  scan if not.
- Reproduce a specific "search doesn't find X" report and check the
  actual `tsvector`/`tsquery` values generated for both the indexed
  content and the search input, to see where the mismatch is (stemming,
  language config, missing prefix support).
- For a design decision, evaluate actual requirements: is search
  primarily exact/prefix/stemmed matching over a single database's data
  (Postgres FTS fits well), or does it need faceted search, typo
  tolerance/fuzzy matching, cross-service unified search, or very high
  query volume with complex relevance tuning (points toward a dedicated
  search engine)?

## Fix
- Add a GIN index on the `tsvector` column (or a generated/computed
  column combining multiple fields into one `tsvector`) so searches use
  the index instead of scanning and recomputing per row.
- Choose the text-search configuration deliberately (`english`, `simple`,
  etc.) to match actual user expectations, and use the same configuration
  consistently when generating both the indexed `tsvector` and the query
  `tsquery`.
- For prefix-search UX (autocomplete-style, "gree" matching "green"), use
  `tsquery` with the `:*` prefix-match operator on the last term, rather
  than expecting `plainto_tsquery` (which does exact stemmed-term
  matching) to provide it.
- Tune `ts_rank`/`ts_rank_cd` weights (the `setweight` function when
  building the `tsvector`) so more important fields (title) contribute
  more to ranking than less important ones (body text), matching actual
  user expectations of relevance.
- Migrate to a dedicated search engine specifically when the real
  requirement outgrows what's described above: fuzzy/typo-tolerant
  matching, faceted filtering combined with search, sub-100ms search
  latency at high query volume with complex scoring, or unifying search
  across multiple data sources/services -- not preemptively, since it
  adds real operational complexity (a second system to run, keep in
  sync, and operate).

## Pitfalls
- Adding a dedicated search engine before Postgres FTS has actually been
  tried and found insufficient adds a whole additional system (indexing
  pipeline, sync/consistency between it and the database, operational
  overhead) for a problem Postgres might have solved adequately.
- Forgetting to keep the `tsvector` column updated when the underlying
  text columns change (via a trigger or application-level update)
  reintroduces a cache-invalidation-style staleness bug specific to
  search: the indexed content silently drifts from the real current data.
- Testing search only with the exact terms present in the sample data
  misses realistic mismatches (plurals, synonyms, typos) that real users
  will actually type -- test with realistic, imperfect query terms.

## Verify
For an index fix, confirm via `EXPLAIN ANALYZE` that the search query now
uses the GIN index rather than a sequential scan; for a matching/ranking
fix, confirm the specific previously-failing search terms now return the
expected results in a reasonable order.
