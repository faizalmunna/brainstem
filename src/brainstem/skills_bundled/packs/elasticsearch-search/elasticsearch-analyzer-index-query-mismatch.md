---
name: elasticsearch-analyzer-index-query-mismatch
description: A full-text query behaves unexpectedly because a different analyzer tokenizes or stems terms differently at index time versus query time.
triggers: ["search not finding obvious match elasticsearch", "analyzer mismatch", "why doesn't this term match", "stemming inconsistent search results", "query time vs index time analyzer", "custom analyzer not applied to search"]
permissions: ["READ"]
---

## Symptom
A search for a term that clearly appears in a document's text returns no
results, or returns inconsistent results depending on capitalization,
pluralization, or minor spelling variants -- despite the field being
mapped as `text` and containing what looks, to a human reading
`_source`, like an obvious match.

## Likely causes
1. **A custom analyzer is set as the field's `analyzer` (used at both
   index and search time by default) but a query explicitly overrides
   `analyzer` or uses a different query type that applies a different
   default** -- e.g. the field indexes with a language-specific stemmer
   but a `match` query's search analyzer was overridden to `standard`,
   so stemmed index tokens (`"running"` -> `"run"`) never match the
   unstemmed query token (`"running"`).
2. **`search_analyzer` is explicitly configured differently from
   `analyzer`** (a legitimate, sometimes intentional setup, e.g. for
   synonym expansion only at query time) but the difference produces
   unexpected tokenization that wasn't accounted for when the query
   behavior was designed or later changed.
3. **A multi-field's base field and `.keyword` sub-field are conflated in
   the query** -- a `term` query (which does not analyze its input at
   all) run against the analyzed base field expects an exact token match
   against whatever the analyzer produced, so a `term` query for the
   literal user-typed string against a stemmed/lowercased field silently
   fails to match the transformed token.
4. **An index was reindexed or its analyzer settings changed, but old
   documents were never reindexed with the new analyzer** -- so identical
   queries match newer documents but not older ones, since each
   document's indexed tokens reflect whatever analyzer was active when
   *that document* was indexed, not the analyzer currently configured.

## Diagnose
- Use `GET /<index>/_analyze` with the field's actual index-time analyzer
  and a sample document's text to see the exact tokens produced, then
  repeat with the query text and the search-time analyzer
  (`GET /<index>/_analyze` accepts `"field": "<fieldname>"` to resolve
  the analyzer automatically, or specify `"analyzer"` explicitly) --
  compare the two token lists directly rather than guessing.
- Check the field's mapping (`GET /<index>/_mapping/field/<fieldname>`)
  for distinct `analyzer` and `search_analyzer` settings -- if both are
  absent, defaults apply uniformly and mismatch is more likely a query-
  construction bug (wrong query type, unintended `analyzer` override)
  than a mapping issue.
- For a `term`/`terms` query returning nothing unexpected, confirm
  whether the target field is analyzed `text` (where `term` queries
  against raw untransformed input are a common mistake) versus `keyword`
  (where `term` queries are the correct tool).
- If behavior differs between older and newer documents, check the
  index's mapping/settings change history and whether affected older
  documents were reindexed after any analyzer change -- Elasticsearch
  applies the analyzer active at index time per-document, not
  retroactively.

## Fix
- Align the query construction with the field's actual configured
  analyzer: use `match`/`match_phrase` (which analyze the query text
  through the field's search analyzer automatically) against analyzed
  `text` fields, and reserve `term`/`terms` for exact, unanalyzed
  `keyword` fields or values already known to match indexed tokens
  exactly.
- If `search_analyzer` is intentionally different from `analyzer` (e.g.
  synonym expansion only at query time to avoid bloating the index with
  every synonym variant), document that intent explicitly in the mapping
  and verify the specific token transformation with `_analyze` whenever
  either side changes, rather than assuming symmetry.
- For documents indexed under a since-changed analyzer, reindex them
  (see `elasticsearch-zero-downtime-reindex-for-mapping-fix`) so all
  documents in the index reflect consistent tokenization -- there is no
  way to retroactively re-tokenize already-indexed documents in place.
- When designing a new analyzer chain, explicitly decide and test
  whether the same analyzer should apply at both index and query time
  (the common case) versus a deliberately asymmetric setup, rather than
  discovering the mismatch after search behaves unexpectedly in
  production.

## Pitfalls
- Assuming `_source` content directly reflects what's searchable is the
  core misconception behind most analyzer confusion -- `_source` is the
  original JSON, completely separate from the analyzed tokens actually
  stored in the inverted index; always verify with `_analyze`, not by
  eyeballing `_source`.
- Changing an analyzer on an index template affects only future indices
  or requires a reindex for the current one -- assuming a settings change
  retroactively re-tokenizes existing documents is a common and costly
  mistake that leads to "it's still broken" reports after a fix was
  "applied."
- Adding aggressive stemming or a broad synonym filter to fix one missed
  match can cause over-matching elsewhere (unrelated terms sharing a stem
  now considered equivalent) -- verify the change against a representative
  query set, not just the single reported miss.

## Verify
Use `_analyze` to confirm the query text and a known matching document's
field both produce overlapping tokens through their respective
analyzers, then re-run the originally failing search and confirm it now
returns the expected document, and spot-check a few previously-working
queries to confirm no regression from the analyzer change.
