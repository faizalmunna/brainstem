---
name: rag-chunk-overlap-duplicate-retrieval-wastes-context
description: Chunk overlap settings cause the same sentence or fact to appear in multiple retrieved chunks, wasting context budget without adding information.
triggers: ["same sentence appears twice in retrieved context", "retrieved chunks are mostly duplicated text", "top-k results are near identical", "overlap causing redundant chunks", "context window full of repeated content"]
permissions: ["READ"]
---

## Symptom
Inspecting the chunks passed to the LLM for a given query shows two or more of the top-k chunks sharing substantial overlapping text -- the same paragraph or sentence appears near-verbatim in multiple "different" retrieved chunks. Effective information density of the context window is lower than top-k would suggest (k=5 chunks might contain only 3 chunks' worth of unique information), inflating token cost and, in cases with a fixed context budget, crowding out genuinely different relevant content that would otherwise have been retrieved.

## Likely causes
1. **Chunk overlap is configured as a large fraction of chunk size** (e.g., 200-token overlap on 500-token chunks) specifically to avoid the split-fact-across-chunks problem, but as a side effect, adjacent chunks are now similar enough in content that they both embed close together in vector space and both get retrieved for the same query, doubling up on the same information.
2. **The same source content was ingested more than once** -- a document exists in the corpus under two different source paths/versions (a PDF and its HTML mirror, a document re-ingested after a partial pipeline failure without deduping against what's already indexed), producing genuinely duplicate chunks rather than merely overlapping ones.
3. **No deduplication or diversity mechanism exists at the retrieval-ranking stage** -- pure top-k-by-similarity-score retrieval has no built-in penalty for a candidate being highly similar to another already-selected candidate, so if the corpus contains near-duplicate content, standard top-k will happily return several near-identical results instead of diversifying.
4. **Multiple chunking passes or re-indexing attempts left artifacts from an old chunking configuration alongside the new one**, similar in mechanism to the stale-chunks-after-reindex problem but specifically produced by chunk-size/overlap parameter changes rather than source-content changes.

## Diagnose
- For a query returning suspiciously similar chunks, compute pairwise text similarity (exact substring overlap or embedding cosine similarity) between the retrieved chunks directly -- a high overlap percentage confirms duplication rather than merely related-but-distinct content.
- Check the chunk metadata (source document ID, chunk start/end offsets) for the duplicated chunks: if they come from the same document at adjacent, heavily-overlapping offsets, this points to the overlap-configuration cause; if they come from different document IDs entirely, this points to duplicate source ingestion.
- Query the vector store for a count of chunks per source document and compare against an expected count given document length and chunk size -- a document with roughly double the expected chunk count is a concrete signal of duplicate ingestion.
- Review the overlap setting as a percentage of chunk size across the corpus's chunking config -- overlap exceeding roughly 20-30% of chunk size is a strong candidate for causing retrieval-time duplication rather than just safety margin.

## Fix
Reduce overlap to the minimum needed to prevent boundary splits (informed by the actual dependency distances found while debugging the split-fact problem, not a large round number chosen defensively) rather than treating "more overlap is safer" as a free lunch. Add deduplication at retrieval time: after initial top-k candidate retrieval, apply a diversity-aware re-ranking step (e.g., Maximal Marginal Relevance) that penalizes selecting a candidate highly similar to one already selected, so the final context set maximizes unique information coverage rather than pure similarity rank. For duplicate-source-ingestion cases, add a content-hash or canonical-source check at ingestion time that detects and skips (or explicitly merges/versions) a document already present in the index under a different path.

## Pitfalls
- Setting overlap to zero to eliminate duplication entirely reintroduces the split-fact-across-chunk-boundaries failure mode -- overlap and duplication are a tradeoff to tune, not a problem with a zero-overlap solution.
- Deduplicating purely on exact text match misses near-duplicates that differ by a few words (different chunk boundary placement catching slightly different surrounding sentences around the same core content) -- use embedding similarity or fuzzy matching for dedup, not exact string equality alone.

## Verify
Re-run a previously-affected query and inspect the retrieved chunk set for pairwise similarity, confirming it has dropped below the dedup threshold; measure the average unique-information ratio (e.g., via manual review or embedding-similarity clustering) across a sample of queries before and after the fix to confirm effective context density improved without reintroducing boundary-split failures on the same test cases used in the split-fact skill's verification.
