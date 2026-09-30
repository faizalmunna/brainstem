---
name: rag-query-rewriting-expansion-hurts-certain-query-types
description: A query rewriting or expansion step added to improve retrieval actually makes results worse for short, specific, or already well-formed queries.
triggers: ["query rewriting made search worse", "HyDE hurts retrieval for some queries", "query expansion adds irrelevant terms", "rephrased query performs worse than original", "LLM query rewrite dilutes search intent"]
permissions: ["READ"]
---

## Symptom
After adding a query rewriting/expansion step (an LLM paraphrasing the user's query, HyDE-style hypothetical-document generation, or automatic synonym/term expansion) to improve recall for vague or conversational queries, retrieval quality improves for some queries but visibly regresses for others -- particularly short, already-precise queries (an exact product name, an error code, a well-formed technical term) where the rewritten version is longer, more generic, or introduces tangential terms that pull the top-k results away from the original intent.

## Likely causes
1. **The rewriting step is applied uniformly to every query regardless of how well-formed the original already is**, so a query that was already optimal (a precise noun phrase or exact identifier) gets needlessly "improved" into a more verbose or generic paraphrase that embeds less distinctively.
2. **An LLM-based query rewriter hallucinates plausible-sounding but incorrect specificity** -- asked to expand a vague query, it can invent assumed details (a specific product line, a specific timeframe) not present in the original intent, and the expanded query now retrieves confidently for the wrong assumption.
3. **HyDE-style approaches (embedding a hypothetical answer instead of the query) work well when the hypothetical answer resembles real documents in the corpus, but backfire when the corpus's actual writing style/structure differs from what the LLM imagines** -- e.g., the LLM generates a hypothetical prose paragraph but the corpus consists of terse structured reference tables, so the hypothetical embeds nowhere near the real answer.
4. **Expansion adds synonyms or related terms without weighting them lower than the original query terms**, so the embedded/expanded query drifts semantically toward the added terms' neighborhood, especially when several expansion terms are added to a short original query, diluting rather than clarifying intent.

## Diagnose
- Split a representative eval query set into categories (short/exact queries, vague/conversational queries, question-form queries) and run retrieval metrics with rewriting on vs. off for each category separately -- a regression concentrated in the short/exact category confirms the uniform-application cause specifically.
- For a specific regressed query, log and inspect the actual rewritten/expanded query text side-by-side with the original, and check for added terms/assumptions that weren't in the user's original query -- this makes hallucinated specificity or unwanted drift directly visible.
- For HyDE-style approaches, manually compare a generated hypothetical document against a real top-matching document from the corpus for the same query -- if they differ substantially in style, structure, or length, the hypothetical isn't a good proxy for real corpus content.
- Check whether rewriting is conditioned on any signal about query quality/length at all, or unconditionally applied to every incoming query -- an unconditional pipeline is itself evidence for cause 1.

## Fix
Make rewriting conditional rather than universal: apply expansion/rewriting selectively to queries that show signals of being vague, very short in an ambiguous way, or conversational/question-form, while passing already well-formed, specific, or entity/code-bearing queries through unmodified (or in addition to, not instead of, the rewritten form -- retrieve with both and merge/fuse results). When using an LLM rewriter, constrain it explicitly to preserve stated entities and not invent unstated specifics, and validate this with a held-out set of exact-match style queries where "no change" is often the correct rewrite. If HyDE is used, validate the hypothetical-document approach specifically against this corpus's actual document style before adopting it broadly, since its effectiveness is corpus-shape-dependent rather than universal.

## Pitfalls
- Disabling rewriting globally after finding one regression category is an overcorrection that throws away real gains on the vague/conversational queries it was added to help -- fix the conditioning logic rather than removing the capability.
- Tuning the rewriter against only the query types it was designed to help (vague queries) without a regression check against the query types it wasn't designed for (exact queries) is how this silently ships in the first place -- any change to the query path needs eval coverage across all query categories, not just the target one.

## Verify
Re-run the full categorized eval set (short/exact, vague, question-form) with the conditional rewriting logic in place and confirm the short/exact category's metrics return to at least pre-rewriting baseline while the vague/conversational category retains its improvement; spot-check the rewritten query text for 10 real vague queries to confirm no invented specifics are being introduced.
