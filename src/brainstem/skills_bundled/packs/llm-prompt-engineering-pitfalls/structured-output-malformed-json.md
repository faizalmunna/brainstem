---
name: structured-output-malformed-json
description: A prompt asking for JSON output occasionally returns malformed JSON or wraps it in extra prose, breaking a downstream parser that expects strict formatting.
triggers: ["json.decode error from llm output", "model wrapped json in markdown code fences", "downstream parser crashes on model output", "model added explanation before the json"]
permissions: ["READ"]
---

## Symptom
A downstream `JSON.parse`/`json.loads` call intermittently throws on the model's response -- sometimes because the JSON is truncated or has a trailing comma, sometimes because the model wrapped it in a ```json code fence, and sometimes because it prepended "Here's the JSON you requested:" before the actual object. The failure rate is low enough to pass initial testing but high enough to page someone in production.

## Likely causes
1. **No structured-output enforcement mechanism used** -- the prompt asks in natural language for JSON but the API call doesn't use the provider's actual JSON mode / structured output / function-calling schema constraint, so the model is free-texting its way toward JSON-shaped output.
2. **Output truncation from a token limit** -- `max_tokens` is set too low for the actual response size, so long objects/arrays get cut off mid-structure, producing syntactically invalid JSON that looks fine for shorter responses.
3. **The prompt itself is ambiguous about "raw JSON" vs. "JSON in your response"** -- without an explicit instruction to emit *only* the object with no surrounding text, the model defaults to its conversational instinct to explain what it's giving you.
4. **The parser is too strict for a probabilistic text generator** -- expecting byte-perfect single-parse success with zero tolerance for code fences or leading/trailing whitespace, when a thin normalization layer is the actual missing piece, not a prompt problem alone.
5. **Few-shot examples in the prompt itself contain formatting inconsistencies** (e.g. one example has a trailing comma or is embedded in a code fence), teaching the model that these variants are acceptable.

## Diagnose
- Log raw model output (before any parsing/stripping) for every failure and categorize failures: truncated (cut off mid-object), fenced (wrapped in ``` blocks), prefaced (has leading prose), or genuinely invalid syntax (trailing commas, unescaped quotes).
- Check whether `max_tokens` is set with headroom above the largest observed valid response, and check if failures correlate with longer inputs that would produce longer JSON.
- Check whether the API call uses the provider's native structured-output feature (JSON mode, `response_format`, tool/function calling with a schema) versus relying purely on prompt wording.
- Audit the prompt's few-shot examples for consistent, clean JSON formatting with no embedded commentary or code fences.

## Fix
Prefer the provider's native structured-output enforcement (JSON mode, schema-constrained function/tool calling, or grammar-constrained decoding) over prompt-only instructions, since these mechanisms constrain the token sampling itself rather than hoping instructions are followed. When native enforcement isn't available or isn't fully strict, add a defensive parsing layer that strips known wrapper patterns (code fences, leading/trailing prose) before parsing, and treat prompt wording ("respond with ONLY the JSON object, no other text") as a second line of defense, not the primary one. Set `max_tokens` with real headroom above the largest expected valid response, derived from measuring actual response sizes on production-shaped inputs, and detect truncation explicitly (e.g. a response that doesn't end in a closing brace) so it can be retried rather than passed to the parser as-is.

## Pitfalls
Relying solely on regex-stripping the response as the entire fix, with no schema constraint on the model side, just moves the brittleness from the parser into the stripping regex -- new wrapper phrasings the model invents later will break it the same way; the durable fix constrains generation, and the stripping layer is a supplement for the cases native enforcement doesn't fully cover.

## Verify
Build a test set of at least 50 production-representative inputs including the longest/most complex expected outputs, run them through the full pipeline (generation + parsing) with the fix applied, and confirm a 100% parse success rate with zero silent truncation -- not just a spot check of a few short examples that were already passing.
