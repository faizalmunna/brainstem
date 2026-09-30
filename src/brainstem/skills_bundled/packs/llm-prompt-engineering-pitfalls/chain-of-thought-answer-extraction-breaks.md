---
name: chain-of-thought-answer-extraction-breaks
description: A prompt requests step-by-step reasoning before a final answer, but the parsing logic that extracts the final answer breaks when the reasoning format varies slightly.
triggers: ["cant parse the final answer from chain of thought output", "answer extraction regex fails sometimes", "model changed its reasoning format and broke parsing", "final answer section missing or in wrong place"]
permissions: ["READ"]
---

## Symptom
A prompt asks the model to "think step by step" and then give a final answer, with application code that parses out just the final answer (via a regex, a fixed delimiter like "Final answer:", or taking the last line). This works most of the time, but intermittently fails -- the model reasons in a slightly different structure, uses different wording for the final-answer marker, includes the answer inside the reasoning instead of after it, or omits the marker on short/simple inputs -- and the parser either extracts the wrong text or throws.

## Likely causes
1. **The final-answer marker is only requested informally in prose** ("then give your final answer") rather than specified as an exact, consistent literal string or structural format the model is told to reproduce verbatim every time, so the model paraphrases the marker itself with normal generative variance.
2. **The parser assumes a rigid structure** (e.g. "the answer is always the last line" or a specific regex) **that matches the common case but not every valid variant** -- reasoning length and structure naturally vary with input complexity, and a fixed-position assumption breaks whenever reasoning is unusually short or long.
3. **No structural enforcement of the reasoning/answer boundary** -- relying purely on natural-language instruction to keep reasoning and final answer separated, when a structured format (explicit tags, or separate reasoning and answer fields in a JSON schema) would make the boundary machine-parseable rather than inferred.
4. **Simple inputs sometimes skip visible reasoning entirely** -- for trivially easy cases the model may jump straight to an answer without the expected step-by-step preamble, and the parser wasn't built to handle the "no reasoning present" case as a valid variant.
5. **Prompt or model changes shifted default reasoning style** (e.g. switching to a model with a different native reasoning format, or a prompt edit that altered the instruction wording) without updating the extraction logic to match.

## Diagnose
- Collect a sample of raw model outputs across a range of input complexities (trivial, typical, complex) and manually inspect the actual structure of reasoning-plus-answer for each -- check whether the final-answer marker's exact wording and position are actually consistent, or only usually consistent.
- Reproduce specific extraction failures and classify them: marker missing, marker paraphrased differently, answer embedded mid-reasoning, or reasoning skipped entirely for simple inputs.
- Check whether the prompt specifies the final-answer format as an exact literal template versus a loose natural-language request, and whether any output examples in the prompt demonstrate the exact expected marker.
- If using a model with native "thinking"/reasoning-token support, check whether that structured channel is being used (which cleanly separates reasoning from the final response) instead of asking for both in one free-text block with a manual delimiter.

## Fix
Prefer a provider's structured-output mechanism for this exact purpose -- either native extended-thinking/reasoning support that separates reasoning into its own channel from the final response, or a schema-constrained response (e.g. a JSON object with distinct `reasoning` and `answer` fields) -- over a free-text delimiter that depends on the model reproducing exact wording. If neither is available, specify the delimiter as an exact, unmissable literal string in the prompt (with an example showing it verbatim) and make extraction logic tolerant of the delimiter appearing anywhere in the text (search, don't assume position) with an explicit fallback path for when it's missing entirely (e.g. treat the whole response as the answer if no reasoning marker is found, rather than throwing).

## Pitfalls
Tightening the extraction regex to match one specific observed failure case, repeatedly, each time a new variant is found, without ever moving to a structural/schema-based separation, produces an ever-growing pile of special cases that will still miss the next format variant -- the durable fix removes the ambiguity at the source rather than chasing it downstream.

## Verify
Build a test set spanning trivial, typical, and complex inputs (so reasoning length/presence varies naturally) plus any previously observed failure cases, run full extraction against the raw model output for each, and confirm 100% successful extraction with the correct final answer -- including explicit checks for the trivial-input case where reasoning might be minimal or absent.
