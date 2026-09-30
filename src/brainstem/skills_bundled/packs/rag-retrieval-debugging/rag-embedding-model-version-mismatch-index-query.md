---
name: rag-embedding-model-version-mismatch-index-query
description: Retrieval quality drops sharply after a deploy because the embedding model used to embed queries no longer matches the one used to index documents.
triggers: ["retrieval quality suddenly dropped after deploy", "similarity scores all look low now", "embeddings API silently updated", "search got worse after upgrading the embedding model", "vector search returns unrelated results after redeploy"]
permissions: ["READ"]
---

## Symptom
Retrieval was working acceptably, then degraded sharply and uniformly across most queries around a specific date or deploy -- not for one document type but broadly. Cosine similarity scores for even obviously-relevant document pairs are noticeably lower than historical norms, and top-k results look semantically scattered rather than close-but-imperfect.

## Likely causes
1. **The embedding API endpoint was called without pinning a model version**, and the provider silently updated the default model (a common pattern with hosted embedding APIs where "the latest model" is the default unless a specific version string is passed), so newly-embedded queries use a different model than the vectors already sitting in the index.
2. **A re-indexing job partially completed** -- some fraction of documents were re-embedded with a new model/dimension while others retain old vectors, so the index is a silent mixture of two incompatible vector spaces even though every vector has the same dimensionality on disk.
3. **Two different code paths embed text differently** -- e.g., the ingestion pipeline embeds raw chunk text but the query path embeds a reformulated/expanded query string through a different wrapper or preprocessing step (different normalization, truncation, or instruction-prefix conventions for asymmetric embedding models), producing vectors that were never comparable in the first place.
4. **An asymmetric embedding model's required prefix convention was dropped or added inconsistently** -- many embedding models require a `"query: "` vs `"passage: "` prefix on the input text to select the right internal mode, and a missing or swapped prefix on one side silently degrades similarity without erroring.

## Diagnose
- Check the embedding model identifier actually sent in each request (log the exact model string/version, not just the client library default) for both the ingestion path and the query path, and confirm they're byte-identical.
- Query the vector store for the stored embedding dimensionality and compare it against the dimensionality the current query-time model produces -- a dimension mismatch is an immediate, unambiguous confirmation (and would normally error, so also check whether the store silently truncates/pads).
- Take a known-relevant document/query pair, embed both fresh right now with the current code paths, and compute cosine similarity directly outside the full pipeline -- compare that number to the similarity of the same query against the *already-indexed* vector for that document; a large gap between "fresh-fresh" similarity and "fresh-query vs stored-document" similarity confirms a mismatch between what's stored and what's being compared against.
- Check provider changelogs/release notes for the embedding model around the regression date if no version pin exists in the code.

## Fix
Pin the exact embedding model version string in configuration for both ingestion and query paths, sourced from one shared constant/config value rather than duplicated in two places, so they can never silently diverge. Treat an embedding model version change as a breaking schema change requiring a full re-index, not a drop-in upgrade -- never let old and new vectors coexist in the same searchable index; write to a new index/collection and cut over atomically once re-indexing is complete. For asymmetric models, centralize the prefixing logic in one shared embedding-client wrapper used by both ingestion and query code so the query/passage convention can't drift independently.

## Pitfalls
- Re-indexing "in place" by overwriting vectors document-by-document leaves the index in a mixed state for the entire duration of the job (which can be hours for a large corpus), during which retrieval quality is inconsistent and hard to distinguish from random degradation -- always index to a fresh collection and swap.
- Assuming a same-provider "minor version bump" is safe: even small model updates can shift the vector space enough that old and new embeddings are no longer comparable, since there's no guarantee of backward compatibility in embedding geometry across versions.

## Verify
After re-indexing, re-run a fixed benchmark set of query/expected-document pairs and confirm similarity scores and top-k recall return to (or exceed) the pre-regression baseline; add an automated check that asserts the embedding model version string in ingestion and query configs match, failing CI/deploy if they diverge.
