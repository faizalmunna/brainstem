---
name: long-context-instruction-drift
description: A long, accumulating conversation causes the model to lose track of or contradict system instructions that were followed correctly earlier in the same session.
triggers: ["model forgot the system prompt after a long conversation", "model contradicts earlier instructions in long chat", "assistant stops following rules after many turns", "instructions work at start of conversation but not later"]
permissions: ["READ"]
---

## Symptom
Early in a conversation the model reliably follows system-prompt rules (a persona, an output format, a constraint like "never recommend a competitor"), but after many turns of accumulated history -- especially once tool outputs, long pasted documents, or extended back-and-forth are in context -- the model starts contradicting those same rules, as if the system prompt's influence fades relative to the growing conversation history.

## Likely causes
1. **Effective instruction dilution** -- the system prompt is a small, fixed amount of text while the conversation history grows unboundedly, so proportionally the model's attention is dominated by recent turns and the original instructions become a smaller fraction of the effective context that recent content can contradict.
2. **Conflicting or stale information accumulates in history** -- an earlier assistant turn made an assumption or stated something that's since become outdated, and later turns build on that stale statement instead of the original instructions, compounding across turns.
3. **No periodic reinforcement of critical constraints** -- the system prompt is sent once and never restated, so as history grows, nothing in the prompt actively counteracts drift; some providers/patterns benefit from restating hard constraints closer to the end of context where recency has more influence.
4. **Context window truncation silently drops the system prompt or early turns** -- if the application's context management trims the oldest messages to fit a token budget without protecting the system prompt, the original instructions may partially or fully fall out of context without any explicit signal that this happened.
5. **Genuine capacity limits on very long contexts** -- even well within the stated context window, model performance on needle-in-a-haystack-style instruction retrieval measurably degrades as context grows, a documented property of long-context behavior, not just a prompting mistake.

## Diagnose
- Reproduce the drift with a scripted long conversation and check, turn by turn, at what point the model first deviates from a specific rule -- this pinpoints whether it's gradual dilution or a sudden break tied to a specific event (e.g. a large document paste, a truncation point).
- Log the exact context sent to the model on the turn where drift is observed and confirm the system prompt is actually present, verbatim, in that request -- rule out silent truncation before assuming it's a model attention issue.
- Check the token count of the conversation at the point of drift relative to the model's context window and relative to where the application's own truncation/summarization logic kicks in.
- Test whether restating the critical constraint as a short reminder appended near the end of the context (not just at the very start) recovers correct behavior at the same conversation length -- if yes, this confirms a recency/positional effect rather than the model "forgetting" in a deeper sense.

## Fix
For constraints that must hold regardless of conversation length, don't rely solely on a system prompt sent once at the start -- reinforce critical rules periodically, either by re-injecting a short constraint reminder every N turns or immediately before the final response generation, so the rule is present near the position the model weights most heavily. Manage context growth deliberately: summarize or prune older turns that are no longer decision-relevant instead of letting raw history grow unbounded, and always protect the system prompt (and any hard constraints) from truncation logic that trims by simple recency. For applications where a hard constraint is safety- or business-critical, don't rely on prompt-level persistence alone -- add an output-side check that validates the final response against the constraint before it's returned, independent of whether the model "remembered" to apply it.

## Pitfalls
Simply making the system prompt longer and more emphatic ("REMEMBER THIS IS VERY IMPORTANT: ...") without addressing context growth or truncation is a common but weak fix -- it may buy a few more turns of compliance but doesn't address the underlying dilution/truncation mechanism, and an overly aggressive, repetitive system prompt can itself degrade output quality by crowding out task-relevant content.

## Verify
Run the same scripted long conversation used in Diagnose past the length where drift was originally observed, with the fix applied, and confirm the constraint holds at that turn count and beyond -- ideally testing at 1.5-2x the length where the original failure occurred, not just just past the original failure point.
