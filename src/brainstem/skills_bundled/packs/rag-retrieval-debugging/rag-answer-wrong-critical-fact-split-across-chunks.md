---
name: rag-answer-wrong-critical-fact-split-across-chunks
description: Retrieval returns chunks that are individually relevant yet the generated answer is wrong because the one fact needed spans two adjacent chunks.
triggers: ["retrieval looks right but the answer is wrong", "the answer is missing a detail that's in the document", "chunk boundary cut off important context", "RAG gives half the answer", "table row split across chunks gives wrong number"]
permissions: ["READ"]
---

## Symptom
The retrieved chunks, inspected manually, clearly contain content related to the question, and the top-k results look reasonable in a similarity-score sense -- yet the final answer is incomplete, subtly wrong, or contradicts the source document. Common concrete cases: a clause like "except for customers in the EU, who instead..." lands in a different chunk than the rule it's an exception to; a table's header row is in one chunk and its data rows are in the next; a definition ("the Retention Period, as defined in Section 2") is chunked away from every place that uses the term.

## Likely causes
1. **Fixed-size chunking with naive overlap** splits mid-sentence or mid-clause at a character/token count boundary with no awareness of semantic units (sentences, list items, table rows), so a qualifying clause or exception ends up orphaned from the statement it modifies.
2. **Overlap window too small relative to the size of the dependent context** -- a 50-token overlap does nothing when the critical dependency (e.g., a defined term used 500 tokens later) is farther apart than the overlap window, so overlap alone can't be relied on to catch it.
3. **Tables, lists, and code blocks are chunked as if they were prose**, breaking a row/header pairing or a numbered list's item from its lead-in sentence, which loses meaning when read as an isolated fragment (a row of numbers with no header conveys nothing).
4. **The retriever returns only one side of the split** -- even when both chunks exist in the index, top-k similarity scoring may rank only one of the two fragments highly enough to be retrieved, because each fragment alone is a weaker semantic match to the query than the pair would be together.

## Diagnose
- Take the specific wrong answer, find the source location in the original document, and print the exact chunk boundaries around it (chunk start/end offsets) to see literally where the split falls relative to the sentence or table row containing the missing fact.
- Check whether both halves were retrieved for the failing query: log the full ranked list of retrieved chunk IDs (not just top-k) and look for the "other half" chunk just below the cutoff -- if it's at rank k+1 or k+2, this is a top-k/ranking problem compounding a chunking problem, not chunking alone.
- Run the same query against the raw document (grep/full-text search) to confirm the complete fact only exists when both fragments are read together, ruling out a pure hallucination or missing-source-document issue.
- Inspect the chunker's output for the document type in question (contract, table-heavy manual) and count how many chunk boundaries fall inside a table, inside a list item, or immediately after a subordinating conjunction ("provided that", "except", "unless") -- a high rate signals a structural chunking gap, not a one-off.

## Fix
Move from fixed-size chunking to structure-aware chunking that respects semantic boundaries: split on section/paragraph/list-item boundaries first, and only fall back to token-count splitting within an oversized unit. For tables specifically, either keep whole tables as single chunks (with the header repeated into each sub-chunk if the table must be split), or serialize each row with its header inline (e.g., "Column: Value" pairs) so a row is self-contained outside the table's visual layout. For clause-dependency cases (exceptions, defined terms), increase overlap to span at least one full sentence before and after the boundary, or use a sentence-boundary-respecting splitter so overlap never bisects a sentence. The underlying principle: a chunk should be independently interpretable -- if a human shown only that chunk would misunderstand or need more context, the boundary is in the wrong place.

## Pitfalls
- Simply cranking up overlap percentage as a blanket fix bloats the index with near-duplicate content, increases retrieval noise (see the chunk-overlap-duplicate-retrieval skill), and still fails for dependencies farther apart than the new overlap window -- overlap is a mitigation, not a structural fix.
- Making chunks very large to avoid splits at all reduces split incidents but reintroduces the long-document fragmentation problem and dilutes embedding specificity, hurting retrieval precision for narrow queries.

## Verify
Re-run the exact failing query and confirm the answer now includes the previously-missing fact; then construct 5-10 additional test queries targeting other known clause-dependency or table locations in the same document type and confirm each retrieves a chunk that is self-contained enough to answer correctly without needing its neighbor.
