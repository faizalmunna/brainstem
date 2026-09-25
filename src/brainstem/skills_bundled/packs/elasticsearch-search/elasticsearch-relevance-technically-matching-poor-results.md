---
name: elasticsearch-relevance-technically-matching-poor-results
description: Search results technically match the query terms via default BM25 scoring but the top results are low-quality because relevance isn't tuned for the domain.
triggers: ["search results are technically correct but bad", "relevance is bad in elasticsearch", "wrong results at the top of search", "exact match should rank higher", "bm25 not returning best result first", "search quality complaints"]
permissions: ["READ"]
---

## Symptom
Users report that search "doesn't work" even though the returned
documents genuinely contain the query terms -- an exact product-name or
title match ranks below a document that merely mentions the term
incidentally several times, or a query for a well-known short phrase
surfaces long, tangentially-related documents ahead of the obviously
correct one.

## Likely causes
1. **Default BM25 scoring rewards term frequency and field length
   normalization uniformly across all fields**, with no field boosting to
   express that a match in `title` or `sku` is a much stronger relevance
   signal than the same term appearing once in a long `description` or
   `body` field.
2. **No distinction between an exact/phrase match and a loose multi-term
   match** -- a `match` query alone scores any document containing all
   the terms somewhere, without additional scoring boost for the terms
   appearing together, in order, or as a complete match against a
   `keyword`/`.exact` sub-field.
3. **No synonym or domain-vocabulary handling**, so queries using a
   common alternate term (an abbreviation, brand name, or colloquial
   term customers actually type) don't match documents that only use the
   formal/canonical term, silently narrowing recall for large segments
   of real queries -- shows up as *poor coverage* more than *bad
   ordering*, but is often reported the same way ("search is bad").
4. **Length normalization penalizing or rewarding the wrong documents**
   for the domain -- BM25's default field-length normalization assumes
   longer fields are proportionally less relevant per term occurrence,
   which is often wrong for fields like product titles where a short,
   exact title should win decisively over a long description stuffed
   with keywords.

## Diagnose
- Run the underperforming query with `"explain": true` (or the `_explain`
  API against the specific document users expect to rank first) and read
  the scoring breakdown -- identify whether the expected top document is
  scoring low because of missing field boost, missing phrase-match bonus,
  or genuinely not matching a term at all (a recall problem, not a
  ranking problem).
- Compare the query clause structure against the mapping: check whether
  fields the business considers highly relevant (title, name, SKU) are
  boosted at all in the query (`"title^3"` syntax or function score) or
  are being searched with equal weight to low-signal fields.
- Collect a handful of real, representative "bad result" queries from
  support tickets or logs and manually judge what the ideal top-3 should
  be for each -- without this, "relevance is bad" has no measurable
  target to tune against.
- Check whether a synonym filter is configured at all
  (`GET /<index>/_analyze` with the query analyzer against a known
  alternate term) to see if it expands to the canonical term or not.

## Fix
- Boost high-signal fields explicitly in the query (`multi_match` with
  `"fields": ["title^3", "sku^5", "description"]`, tuned by testing
  against the representative query set, not guessed once and left) so
  exact-field matches outweigh incidental mentions in long text.
- Add a `bool` query combining a loose `match` clause (for recall) with a
  `should` clause using `match_phrase` or a `term` query against a
  `.keyword`/`.exact` sub-field for the same content, so a genuinely
  exact or phrase match receives an additive scoring boost over a
  scattered-terms match.
- Add a synonym token filter (`synonym` or `synonym_graph`) to the
  analyzer used at index time (or query time, understanding the tradeoffs
  -- see `elasticsearch-analyzer-index-query-mismatch`) populated with
  actual domain vocabulary gathered from real query logs, not a generic
  thesaurus.
- Use `function_score` with a field-value factor or decay function when
  a non-text signal should influence ranking (recency, popularity,
  in-stock status) -- multiplying BM25 score by a business signal rather
  than only relying on text-match strength alone.

## Pitfalls
- Boosting fields based on intuition rather than the explain output and a
  real judged query set leads to whack-a-mole tuning that fixes one
  reported query while quietly breaking others -- always re-run the full
  judged set after any scoring change, not just the query that prompted
  it.
- Adding synonyms too liberally (near-synonyms that aren't truly
  interchangeable in context) increases recall at the cost of precision,
  diluting relevance for the exact-match queries that were working fine
  -- scope synonym expansion to genuinely interchangeable terms.
- Over-relying on `function_score` boosts for business signals (recency,
  popularity) can drown out actual text relevance if the multiplier isn't
  scaled/capped, making search feel like a sorted list by a business
  metric rather than a text search.

## Verify
Re-run the same representative judged query set used during diagnosis
and confirm the previously-poor top results now rank the manually-judged
best document in the top 1-3 positions; for synonym fixes, confirm via
`_analyze` that the alternate term now expands to match the canonical
indexed term, and check that precision on previously-correct queries
hasn't regressed.
