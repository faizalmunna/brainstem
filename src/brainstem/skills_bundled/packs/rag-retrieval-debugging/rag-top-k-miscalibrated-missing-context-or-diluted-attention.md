---
name: rag-top-k-miscalibrated-missing-context-or-diluted-attention
description: Top-k retrieval count is set too low so relevant chunks are missing, or too high so irrelevant chunks dilute the LLM's attention and inflate cost.
triggers: ["increasing top-k didn't help", "too many irrelevant chunks in context", "answer missing information that's in a lower-ranked chunk", "RAG context window is mostly noise", "retrieval cost too high from large top-k"]
permissions: ["READ"]
---

## Symptom
Two opposite-looking complaints trace back to the same misconfigured parameter. Low top-k: the answer is missing information that a manual check confirms exists in the corpus, and it turns out the relevant chunk was ranked just below the cutoff (rank k+1, k+2). High top-k: answers become vague, occasionally cite irrelevant details, cost per query rises noticeably, and the LLM sometimes visibly prioritizes an irrelevant-but-verbose retrieved chunk over a short, highly relevant one buried in the middle of a long context.

## Likely causes
1. **Top-k was chosen once, arbitrarily (a common default like 3 or 5), without measuring recall@k against a judged query set**, so there's no evidence it matches the actual number of chunks typically needed to answer real queries in this corpus.
2. **Chunk size and top-k weren't tuned together** -- a corpus with small chunks needs a higher k to cover the same amount of source material as a corpus with large chunks at a lower k, so a k value copied from a different project's configuration (with different chunk sizes) is miscalibrated by construction.
3. **"Lost in the middle" effects**: LLMs are measurably less reliable at using information placed in the middle of a long context versus the beginning or end, so simply raising k to "be safe" doesn't linearly improve answer quality once the context is long enough to trigger this effect -- more retrieved chunks can actively hurt even when they're all technically relevant.
4. **No re-ranking step after initial retrieval** -- a larger top-k pulls in more borderline-relevant chunks from the first-pass retriever (which is optimized for recall, not precision) with nothing downstream to reorder or filter them before they all get passed to the LLM as equally-weighted context.

## Diagnose
- Using a judged query set, compute recall@k for several k values (e.g., 3, 5, 10, 20) and plot how many additional relevant chunks are captured at each increment -- find the point of diminishing returns rather than guessing.
- For specific "missing information" complaints, check the rank of the actually-relevant chunk in the full ranked list; if it consistently falls in a narrow band just above the current k, that's direct evidence to raise k or improve ranking precision, not necessarily both.
- For "diluted answer" complaints, log the full set of chunks actually passed to the LLM for a sample of queries and manually score what fraction are genuinely relevant to the question -- a low relevant-fraction at the current k confirms dilution independent of any "lost in the middle" positioning effect.
- Measure and compare answer quality (not just retrieval recall) at multiple k values in an A/B or offline eval to find where end-to-end quality peaks -- recall keeps improving with higher k but end-to-end answer quality often peaks earlier and then declines.

## Fix
Tune top-k empirically against a judged query set and end-to-end answer-quality eval together, not retrieval recall alone -- pick the k that maximizes downstream answer quality, which is often lower than the k that maximizes raw recall. Add a re-ranking stage (a cross-encoder or LLM-based re-ranker) between a higher-recall first-pass retrieval (larger initial k, e.g., 20-50) and a smaller final set actually passed to the LLM (e.g., 3-8), so the system gets the recall benefit of casting a wide net without paying the dilution cost of passing everything through. Where context ordering matters, place the highest-confidence chunks at the beginning and/or end of the context rather than in retrieval-score order alone, accounting for position-sensitivity in the underlying model.

## Pitfalls
- Raising top-k as a reflexive fix for any "missing information" complaint without checking whether the real problem is retrieval ranking (the right chunk exists but scores too low) versus true top-k cutoff -- if ranking is the issue, more k just means more noise before eventually reaching the right chunk, at higher cost.
- Adding a re-ranker but feeding it the same narrow first-pass candidate set instead of widening initial retrieval -- the re-ranker can only reorder what it's given, so it can't recover a truly missing chunk that never made the first-pass candidate list.

## Verify
Re-run the judged query set at the newly chosen k (and re-ranker configuration, if added) and confirm recall@k and end-to-end answer-quality score both meet or exceed prior bests simultaneously; check average tokens-per-query and cost to confirm the change didn't silently regress cost while chasing quality.
