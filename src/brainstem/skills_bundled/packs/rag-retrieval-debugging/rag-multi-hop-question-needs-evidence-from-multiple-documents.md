---
name: rag-multi-hop-question-needs-evidence-from-multiple-documents
description: A question requires combining facts from two or more unrelated documents, but single-pass top-k retrieval only surfaces chunks for one part of the question.
triggers: ["RAG can't answer questions that span multiple documents", "multi-hop question fails in RAG", "system answers half the compound question", "comparison question between two documents fails", "retrieval only finds one of the two things I asked about"]
permissions: ["READ"]
---

## Symptom
A question that requires connecting information from two separate source documents ("Which of our two vendors has the shorter payment terms, according to their respective contracts?" or "Did the Q3 incident have the same root cause as the one described in the Q1 postmortem?") gets a confidently wrong or one-sided answer -- the system retrieves good chunks for one half of the question and either ignores the other half entirely or fabricates it, because nothing in a single top-k retrieval pass surfaced the second document at all.

## Likely causes
1. **A single embedding of the full compound question is used for one retrieval pass**, and that embedded vector ends up closest to whichever sub-topic is more prominent or more textually dominant in the question, systematically underweighting the other sub-topic's relevant documents in the similarity ranking.
2. **Top-k is tuned for single-fact queries and is too small to surface both relevant documents even if they're both reasonably ranked** -- if each sub-topic's best chunk sits around rank 4-6, a k of 5 arbitrarily includes one and excludes the other depending on minor score differences.
3. **No query decomposition step exists** -- the system has no mechanism to recognize a question is compound/comparative and split it into independent sub-queries retrieved separately, so it's architecturally a single-hop retriever being asked a multi-hop question.
4. **Even when both documents are retrieved, the prompt doesn't clearly attribute which chunk belongs to which entity being compared**, so the LLM has the right raw material but conflates or misattributes facts between the two sources during generation.

## Diagnose
- Manually split the compound question into its sub-questions and run each through retrieval independently -- confirm whether each sub-question, in isolation, successfully retrieves its relevant document (if yes, this isolates the problem to the compound-query retrieval step, not a general retrieval failure for either document).
- Inspect the full ranked retrieval list (not just top-k) for the original compound query and check whether the "missing" document's best chunk is present but ranked below the cutoff versus entirely absent from the ranking -- distinguishes a top-k sizing issue from a genuine similarity/relevance ranking issue.
- Check whether the pipeline has any query-classification or decomposition step at all by tracing the code path for a compound query -- confirms whether this is a missing-capability gap architecturally, not a tuning issue.
- If both chunks are confirmed retrieved and passed to the LLM, but the answer still conflates them, inspect the assembled prompt for whether each chunk is labeled with its source document identity, ruling in/out an attribution-in-generation cause separately from a retrieval cause.

## Fix
Add a query decomposition step for questions that show comparative or compound structure (detectable via simple heuristics -- "compare," "difference between," "both," multiple named entities -- or via an LLM classification/decomposition call for ambiguous cases): split into independent sub-queries, retrieve separately for each, and then combine the retrieved sets (clearly labeled by which sub-query/entity they answer) into the final context. This converts a single hard retrieval problem into several easier ones that each get their own top-k budget, rather than forcing one embedding to represent two different information needs. When assembling the combined context, explicitly tag each chunk with its source document/entity in the prompt so the generation step can attribute facts correctly rather than relying on the LLM to infer which chunk belongs to which side of the comparison.

## Pitfalls
- Applying decomposition to every query indiscriminately adds latency and cost (an extra classification/decomposition LLM call) for the majority of queries that are genuinely single-hop -- gate decomposition behind a cheap classification step or heuristic rather than running it universally.
- Decomposing into sub-queries but then merging results back with a single shared top-k budget across both (e.g., top-5 total instead of top-5 per sub-query) recreates the original dilution problem where one sub-topic's results crowd out the other's -- give each sub-query its own retrieval budget.

## Verify
Build a small test set of known multi-hop/comparative questions with documented expected source documents for each sub-part, run them through the decomposition-enabled pipeline, and confirm chunks from all required documents now appear in the final context and the generated answer correctly addresses every sub-part rather than just the dominant one.
