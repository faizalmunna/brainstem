---
name: rag-fixed-chunk-size-fragments-long-structured-documents
description: A chunking configuration tuned on short documents badly fragments long, hierarchically-structured documents like contracts or technical manuals.
triggers: ["long contracts return bad chunks", "technical manual retrieval is fragmented", "chunking works for short docs but not long ones", "lost the section context in a long PDF", "retrieval ignores document hierarchy"]
permissions: ["READ"]
---

## Symptom
Retrieval performs well on short documents (FAQs, short articles, emails) but noticeably worse on long structured documents -- a 200-page technical manual or a 40-page contract. Retrieved chunks for these documents read as generic, hard-to-place fragments ("...shall be governed by the terms set forth herein...") with no indication of which section, clause number, or chapter they came from, and the LLM's answer sometimes misattributes a clause to the wrong context (e.g., applies a limitation from Section 12 as if it were general policy).

## Likely causes
1. **One global chunk-size/overlap setting is applied uniformly regardless of document structure**, so a document with deep hierarchy (parts, sections, subsections, clauses) gets sliced by raw character count with no regard for where a subsection actually ends, while a flat short document happens to fit the same setting well by coincidence.
2. **Section/heading metadata is discarded during text extraction**, typically because the ingestion pipeline extracts plain text from a PDF/DOCX before chunking, losing heading styles, numbering, and hierarchy that would otherwise let the chunker align splits to logical sections.
3. **No hierarchical context is attached to chunks after splitting** -- even if splits happen to align with a subsection, the chunk itself doesn't carry "Part III > Section 4.2 > Termination" as metadata or a prepended header, so retrieved chunks lose their place in the document's structure once separated from it.
4. **Chunk size chosen by averaging across a mixed corpus** during initial tuning, landing on a size that's a reasonable compromise for short documents but is far too small relative to the natural unit size (a full clause, a full procedure) in long structured documents, causing excessive fragmentation of what should be one retrievable unit.

## Diagnose
- Pull 10 chunks from a poorly-performing long document and check whether any human reading just the chunk text (no surrounding context) could identify what section/topic it belongs to -- if not, structure has been lost.
- Compare the configured chunk size against the median length of a natural section/subsection in the document type (count characters between headings in a sample of contracts or manuals) -- if chunk size is a fraction of the natural unit size, splits are cutting across meaningful boundaries by construction.
- Check the text-extraction step's output directly (before chunking) for whether heading markers, numbering, or structural markup (Markdown headers, DOCX heading styles, PDF bookmark/outline data) survived extraction -- if the extractor flattens everything to plain paragraphs, hierarchy is lost upstream of chunking, not in the chunker itself.
- Compare retrieval eval metrics (see the missing-retrieval-eval-metric skill) segmented by document length/type; a clear precision drop specifically on long structured documents versus short ones confirms the effect is structural rather than a general quality issue.

## Fix
Use a hierarchy-aware chunking strategy: parse structural markers (headings, numbered sections, DOCX styles, PDF outline/bookmarks) during extraction and chunk along those boundaries first, falling back to size-based splitting only within an oversized leaf section. Prepend each chunk with its hierarchical breadcrumb (e.g., "Part III: Termination > Section 4.2: Notice Requirements") so the chunk is self-describing even in isolation, and store the breadcrumb as retrievable metadata so it can also be surfaced to the LLM as context, not just baked into the embedded text. For very long, deeply-nested documents, consider a two-level retrieval approach: retrieve at the section level first (or generate section summaries as a first-pass index), then retrieve fine-grained chunks within the top candidate sections -- this preserves the ability to distinguish "which subsection is this from" without embedding an entire long section as one oversized chunk.

## Pitfalls
- Choosing one large chunk size to "fix" fragmentation for long documents then quietly hurts short-document retrieval precision by making short-document chunks too coarse -- chunking strategy should branch on document type/length, not use a single global constant tuned for the average case.
- Prepending breadcrumbs to the embedded text without limit can dominate the embedding for short chunks (the breadcrumb becomes a larger fraction of the token count than the actual content), skewing similarity toward matching section titles rather than content -- keep breadcrumbs short and consider embedding content and breadcrumb separately if this shows up in eval.

## Verify
Re-run the retrieval eval set specifically on long structured documents and confirm precision/recall at k now matches short-document performance; manually inspect a sample of retrieved chunks from a long contract and confirm each one is now self-identifying (states or implies its section) without needing the full document for context.
