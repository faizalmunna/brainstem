---
name: prompt-token-bloat-cost-creep
description: Per-request token cost and latency grow steadily over time because a prompt template keeps accumulating boilerplate and redundant context that nobody audits.
triggers: ["llm api costs keep going up without more traffic", "prompt got slower over time", "why is our token usage per request increasing", "prompt template has grown huge over many iterations"]
permissions: ["READ"]
---

## Symptom
API cost per request and/or response latency has crept upward over weeks or months without a corresponding increase in traffic volume or task complexity -- tracing it back shows the prompt template itself has grown substantially larger through incremental edits, each individually reasonable, that nobody ever revisited as a whole.

## Likely causes
1. **Accretive editing with no pruning discipline** -- every fix to a prompt problem adds a new instruction, example, or caveat, but nothing is ever removed once the original issue it addressed is no longer relevant (e.g. patched for a model version that's since been upgraded away from), so net length only ever increases.
2. **Redundant context passed on every call** -- the same static reference material, schema definition, or instructions are re-sent in full on every single request when they could be cached (via the provider's prompt caching feature) or reduced to a reference rather than inlined every time.
3. **Conversation history included in full without pruning or summarization**, so a multi-turn interaction's token cost grows quadratically-ish as history is resent on every subsequent turn without ever trimming or summarizing older, less relevant turns.
4. **Few-shot examples accumulate rather than getting curated** -- new examples get added to fix new failure modes but old examples that are no longer pulling their weight (redundant with newer ones, or addressing an issue that's been fixed another way) are never removed.
5. **Over-fetching context for RAG or tool-augmented calls** -- retrieving and injecting more chunks/tool output than the task actually needs "just in case," with no measurement of whether the extra context actually improves output quality.

## Diagnose
- Pull the prompt template's version history (if version-controlled) and chart its token count over time against the timeline of cost/latency increase -- confirm they track together before assuming the prompt is the cause versus a traffic increase.
- Break down the current prompt into sections (system instructions, few-shot examples, retrieved context, conversation history) and measure the token count of each section, to identify which is the largest contributor.
- For each few-shot example, check whether ablating it (temporarily removing it and re-running the eval set) changes output quality at all -- examples with zero measurable impact are dead weight.
- Check whether the provider's prompt caching feature is in use for the static portions of the prompt (system instructions, fixed examples) that don't change per-request, and whether cache hit rate is actually high in production.

## Fix
Treat prompt length as a metric to actively manage, not a side effect to ignore: track token count per request over time the same way latency or error rate is tracked, and set a review trigger (e.g. any 20%+ increase, or a periodic quarterly audit) to prune what's no longer earning its cost. Move static, repeated content (system instructions, fixed reference material, stable few-shot examples) behind the provider's prompt caching mechanism where available, since cached tokens are typically billed and processed differently than fresh ones. For conversation history, implement deliberate summarization or windowing once history exceeds a threshold, rather than resending the full transcript on every turn indefinitely. Curate few-shot examples based on measured marginal contribution (via ablation) rather than letting the set only ever grow.

## Pitfalls
Cutting prompt length aggressively without re-running the evaluation set risks quietly reintroducing the failure mode an example or instruction was originally added to fix -- any pruning pass needs the same regression test discipline as adding content did, not just a token-count target to hit.

## Verify
After pruning/caching changes, measure token count and cost per request against a fixed baseline traffic sample and confirm the reduction, then run the full evaluation/regression suite to confirm output quality metrics haven't regressed as a result of the removed content.
