---
name: rag-stale-chunks-survive-reindex-after-source-update
description: After a source document is updated and re-indexed, the old outdated chunks remain retrievable alongside or instead of the new version.
triggers: ["RAG returns outdated information after document update", "old policy still shows up after we updated it", "reindexing doesn't remove old chunks", "duplicate stale and fresh chunks both retrieved", "deleted document still appears in search results"]
permissions: ["READ"]
---

## Symptom
A source document is edited (a policy changes, a price updates, a page is deleted) and the ingestion pipeline is re-run, but the RAG system continues to surface the old information -- either exclusively, or the old and new chunks are both retrieved and the LLM picks one arbitrarily or blends them into a contradictory answer. This is especially dangerous because it's silent: there's no error, just intermittently wrong answers that look like normal retrieval noise.

## Likely causes
1. **The ingestion pipeline only inserts new chunks and never deletes or marks stale chunks tied to the old version of the document**, because the pipeline was built around an "add documents" mental model without a corresponding "remove/replace document" step, so re-processing a changed document is additive rather than a true update.
2. **Chunk IDs are content-hash-based or randomly generated rather than deterministically tied to (document ID, chunk position)**, so re-chunking a changed document produces an entirely new set of chunk IDs that don't overwrite the old ones in the vector store -- both old and new IDs coexist as separate entries.
3. **A caching layer (embedding cache, retrieval result cache, or CDN in front of a RAG API) serves stale results** for a period after re-indexing completes, independent of whether the underlying index itself was correctly updated.
4. **Deletion is implemented as a soft delete or metadata flag that the retrieval query doesn't actually filter on** -- the document is marked `deleted: true` or `version: old` in metadata, but the retrieval query never applies that filter, so soft-deleted content remains fully retrievable.

## Diagnose
- Pick a document known to have been updated, and query the vector store directly (not through the full RAG pipeline) for all chunks whose metadata references that document's source ID -- check whether both old-version and new-version chunks are present simultaneously.
- Check the ingestion pipeline code/job logs for the update path specifically: does updating a document trigger a delete-by-source-id operation against the vector store before or after inserting new chunks, or does the pipeline only ever call an insert/upsert operation?
- If chunk IDs are inspected and found to differ between runs for the same source document, confirm whether the vector store's upsert semantics are being relied on (upsert only overwrites if the ID matches exactly) -- non-deterministic IDs silently defeat upsert-based update logic.
- Check for a caching layer between the retrieval API and the client (response cache, CDN, application-level memoization) with a TTL that could explain a delayed-but-eventually-correct update, which would point to caching rather than indexing as the root cause.

## Fix
Make document updates an explicit delete-then-insert (or true upsert keyed on a deterministic ID) operation in the ingestion pipeline: before inserting newly-chunked content for a source document, delete all existing vector store entries tagged with that document's source ID, so there's never a window where old and new chunks coexist beyond the atomic update itself. Use deterministic chunk IDs derived from (source document ID, stable chunk index or heading path) rather than random UUIDs or content hashes, so re-ingesting the same logical chunk position naturally overwrites rather than duplicates. If soft-deletes are used for auditability, ensure the retrieval query path always applies an `is_current`/`deleted=false` filter, and treat that filter as load-bearing enough to have its own test coverage.

## Pitfalls
- Deleting old chunks only from the primary vector index but forgetting a secondary keyword/BM25 index used for hybrid search, leaving stale content retrievable through one path but not the other -- any secondary index needs the same delete-on-update guarantee.
- Doing delete-then-insert as two separate non-atomic operations in a high-traffic system creates a brief window with zero results for that document between the delete and the insert completing -- for high-traffic corpora, prefer an atomic swap (index to a new version tag, then flip a pointer/alias) over delete-then-insert.

## Verify
Update a test document with a clearly distinguishable marker (e.g., change a fact to an obviously different value), re-run the ingestion pipeline, then query the vector store directly for that document's source ID and confirm only new-version chunks exist; run the corresponding RAG query end-to-end and confirm the answer reflects the update, not the prior value.
