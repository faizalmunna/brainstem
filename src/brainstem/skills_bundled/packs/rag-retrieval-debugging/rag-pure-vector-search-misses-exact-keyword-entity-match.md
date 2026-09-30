---
name: rag-pure-vector-search-misses-exact-keyword-entity-match
description: Vector-only retrieval ranks a semantically similar chunk above the chunk containing the exact product code, error code, or entity name the user actually typed.
triggers: ["exact error code not found by RAG", "product SKU search returns wrong item", "vector search misses exact match", "semantic search ignores literal keyword", "need hybrid search keyword plus vector"]
permissions: ["READ"]
---

## Symptom
A user searches for a specific, unambiguous token -- an error code ("ERR_5512"), a part number ("SKU-88213-B"), a person's name, or a short exact phrase -- and the RAG system returns chunks that are topically related but don't contain that literal token, while a chunk that does contain the exact token ranks lower or is missing from top-k entirely. The complaint is usually phrased as "it can't even find the exact thing I searched for."

## Likely causes
1. **Dense embedding models represent rare or out-of-vocabulary tokens (codes, IDs, SKUs, uncommon proper nouns) poorly**, because these tokens are underrepresented in the model's training data and get embedded close to generic/average vectors rather than in a way that distinguishes them sharply from similar-looking tokens.
2. **Pure cosine/dot-product similarity ranking has no mechanism for rewarding exact lexical overlap** -- a chunk that shares the surrounding topic and vocabulary but not the specific identifier can score a higher similarity than a chunk containing the literal identifier buried in otherwise dissimilar phrasing.
3. **No keyword/full-text index exists alongside the vector index at all**, so there's no fallback path capable of doing exact or fuzzy lexical matching regardless of how retrieval is tuned -- the system is architecturally vector-only.
4. **Tokenization/chunking normalizes or strips characters that matter for exact identifiers** (case-folding, hyphen/underscore stripping, stemming) before embedding, so the query's exact identifier and the document's exact identifier are no longer represented identically even in a keyword search layer, if one exists.

## Diagnose
- Take a known failing query (a specific code/ID known to exist verbatim in the corpus) and run a plain full-text/grep search over the raw documents to confirm the exact string exists -- rules out a missing-data explanation.
- Run the same query through the vector retriever alone and inspect the rank of the chunk containing the exact string in the full ranked list (not just top-k) -- if it's present but ranked low, this is a scoring/weighting problem; if absent even at rank 50+, the embedding is failing to represent the token distinctively at all.
- Check whether a keyword/BM25-style index exists in the stack at all (Elasticsearch, a BM25 library, a Postgres full-text index, a sparse retriever) -- if not, this is a missing-capability gap, not a tuning gap.
- If a keyword index does exist, run the identifier through the same analyzer/tokenizer used at index time (e.g., an `_analyze` call) and check whether it's tokenized in a way that preserves the exact string as a matchable unit.

## Fix
Add a hybrid retrieval path that combines dense vector search with sparse/lexical search (BM25 or equivalent) and merges results, rather than relying on vector similarity alone. A practical pattern: run both retrievers in parallel, then combine scores with reciprocal rank fusion (RRF) or a weighted sum tuned against a judged query set, so a document ranking highly on either signal surfaces even if it doesn't win on the other. For known structured identifiers (SKUs, error codes, ticket numbers), consider an additional exact-match short-circuit: detect identifier-shaped query tokens with a regex/pattern check and issue a direct lexical lookup against a metadata field or keyword index before or alongside the hybrid retrieval, since these queries have one objectively correct answer and don't benefit from semantic fuzziness at all.

## Pitfalls
- Bolting on a keyword index but tuning its weight arbitrarily (e.g., always 50/50 with vector score) rather than validating against real exact-match and semantic-match query examples separately -- the right blend differs by query type, and a single global weight will underserve one category no matter which way it's set.
- Applying the same aggressive text normalization (lowercasing, stemming, stripping punctuation) to the keyword index that's used for prose search, which can silently break exact identifier matching (a stemmer mangling a part number) -- identifier-bearing fields often need a separate, minimally-normalized analyzer.

## Verify
Build a small test set of known exact-identifier queries with a known correct source chunk, run it through the hybrid pipeline, and confirm the correct chunk now appears in the top-1 or top-3 results for all of them; separately confirm the existing semantic-query eval set hasn't regressed from adding the lexical path.
