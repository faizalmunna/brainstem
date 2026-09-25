---
name: rag-llm-ignores-correct-context-favors-prior-knowledge
description: The LLM receives correct retrieved context yet answers from its own pretrained knowledge instead, especially when the context conflicts with common belief.
triggers: ["retrieved context is correct but the LLM ignores it", "model hallucinates despite good context", "RAG contradicts the source document it was given", "LLM answers from training data not the provided docs", "context says one thing model says another"]
permissions: ["READ"]
---

## Symptom
Manual inspection confirms the retrieved chunks contain the correct, complete answer, yet the LLM's generated response contradicts them -- most noticeably when the retrieved fact is unusual, recently changed, or conflicts with what's generally true or widely believed (a pricing tier that changed, a deprecated API that the model "knows" is still current, an internal policy that differs from industry-standard practice). This is a generation-stage failure distinguishable from a retrieval failure because the ground-truth answer is demonstrably present in what was passed to the model.

## Likely causes
1. **The prompt doesn't instruct the model to prioritize the provided context over its own knowledge**, so when the model's internal parametric knowledge strongly favors a different answer, generation defaults to the higher-confidence (to the model) prior rather than treating retrieved context as authoritative.
2. **Retrieved context is presented ambiguously in the prompt** -- mixed in without clear delimiting, without a citation/grounding instruction, or positioned in a location in the prompt (e.g., far from the question) where recency/position bias in the model's attention weakens its influence relative to the question itself.
3. **The retrieved chunk states the fact in a way that reads as low-confidence or conditional** (hedged phrasing, buried in a caveat, or presented without enough surrounding confirmation) while the conflicting "common knowledge" answer is stated unconditionally in the model's training data, so the model resolves the apparent tension toward the more confidently-phrased side.
4. **No explicit instruction to say "I don't know" or defer entirely to context** means the model blends retrieved and parametric knowledge into an averaged-sounding answer rather than cleanly picking one, which reads as "ignoring" the context when it's actually partially incorporating it.

## Diagnose
- Reproduce the exact failing prompt sent to the LLM (full context block + question, not a paraphrase) and check whether the system/instruction prompt contains any explicit directive to treat the provided context as authoritative and prefer it over prior knowledge -- absence of this instruction is the single most common cause.
- Test the same retrieved context with a minimal, hardened prompt template ("Answer using ONLY the following context. If the context contradicts general knowledge, trust the context. If the answer isn't in the context, say so.") and see if behavior changes -- isolates whether this is a prompting issue versus a deeper model/context-structuring issue.
- Check where in the prompt the context sits relative to the question and system instructions; for long contexts, test moving the question to appear both before and after the context block, since some models weight information near the end of the prompt more heavily.
- Try the same query with a fact that does NOT conflict with common knowledge and confirm the model uses retrieved context correctly there -- if it does, this confirms the failure is specifically the conflict-with-prior case rather than general context-following ability.

## Fix
Add an explicit grounding instruction in the system/task prompt that states the retrieved context is the authoritative source of truth for this task and must override the model's own background knowledge when they conflict, including an explicit fallback instruction for what to do when context is insufficient ("say you don't know" rather than guessing). Structure the prompt so retrieved context is clearly delimited (XML-like tags or a clear header) and positioned close to the question rather than far upstream in a long prompt. For high-stakes factual domains (pricing, compliance, versioned technical facts), consider requiring inline citation of the specific chunk supporting each claim in the answer -- forcing the model to point at a source measurably increases reliance on provided context because ungrounded claims become visibly unsupported.

## Pitfalls
- Over-correcting with an extremely rigid "ONLY use the context, never say anything else" instruction can cause the model to refuse to answer reasonable follow-up or synthesis questions that require combining retrieved facts with ordinary reasoning (not external knowledge) -- distinguish "don't use outside facts" from "don't reason at all."
- Assuming this is always a generation problem: always re-confirm the retrieved context actually and unambiguously contains the correct answer before tuning the prompt, since a chunk that's topically relevant but subtly incomplete can look like a "the model ignored good context" failure when it's actually a retrieval-completeness failure (see the split-fact-across-chunks skill).

## Verify
Re-run the specific conflicting-fact query with the updated prompt template and confirm the answer now matches the retrieved context; build a small regression set of 10-15 known context-vs-prior-knowledge conflict cases (versioned facts, internal policies that differ from industry norms) and confirm the model sides with context on all of them without breaking unrelated reasoning-style questions.
