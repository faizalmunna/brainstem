---
name: multilingual-prompt-inconsistent-non-english-behavior
description: A prompt tuned and tested only in English produces noticeably worse instruction-following, formatting, or safety behavior when users write in another language.
triggers: ["output quality is worse for non-english users", "json format breaks only for non-english input", "model ignores instructions when user writes in spanish or another language", "safety guardrails weaker in other languages"]
permissions: ["READ"]
---

## Symptom
A prompt performs reliably -- correct formatting, consistent instruction-following, consistent refusal/guardrail behavior -- when tested and used in English, but support tickets or logs reveal meaningfully worse behavior for users writing in other languages: structured output breaks more often, tone/persona instructions are followed less consistently, or safety constraints that reliably hold in English are more easily bypassed in another language.

## Likely causes
1. **All prompt engineering and evaluation was done exclusively in English** -- examples, test sets, and manual spot-checks never included non-English inputs, so any language-dependent fragility in the prompt was never observed before shipping.
2. **Few-shot examples are all written in English**, which both biases the model toward responding in English regardless of input language (unless explicitly instructed otherwise) and gives it a weaker template to follow when the actual conversation is in another language.
3. **Instructions rely on English-specific phrasing or wordplay** that doesn't translate conceptually, or reference formatting conventions (quote styles, number formatting) that differ by locale, causing subtle formatting drift specifically for non-English content.
4. **Safety/guardrail training and prompt-level safety instructions are known to be less robust in lower-resource languages** for many models -- a documented, general property of current LLMs, not specific to any one prompt -- so a prompt that relies purely on instruction-level guardrails (versus provider-level safety systems) inherits this gap.
5. **Structured-output enforcement mechanisms behave differently across languages** in some edge cases (e.g. tokenization differences affecting how reliably a schema-constrained model emits exact field names when the rest of the content is in another script), which is rarely tested because the structural test suite is English-only.

## Diagnose
- Build a small parallel test set: the same set of representative tasks translated into each language the product actually serves, and run the full pipeline (prompt plus parsing/validation) against each language, comparing failure rates directly against the English baseline.
- Check the language composition of the few-shot examples in the prompt -- if 100% are English while the product serves a multilingual user base, that mismatch is a primary suspect.
- For safety-sensitive prompts, test known guardrail-bypass patterns translated into each supported language, not just English, since guardroom robustness is well documented to vary by language for many models.
- Check whether structured-output failures specifically correlate with non-English input by segmenting the malformed-JSON/format-failure logs (if tracked) by input language.

## Fix
Include representative non-English examples in both the few-shot set and the evaluation/regression suite for every language the product actually supports, rather than assuming English-tuned behavior generalizes. Make formatting instructions language-agnostic and explicit rather than relying on English-specific convention (e.g. specify the exact expected structure regardless of response language, rather than assuming the model will naturally apply the same formatting habits across languages). For safety-critical behavior, don't rely solely on prompt-level instructions to hold across languages -- layer in provider-level safety systems and, where available, language-aware moderation/classification on top, since this is a known model-level limitation that prompt wording alone is unlikely to fully close.

## Pitfalls
Fixing the issue by simply instructing the model to "always respond in English" as a workaround, when the product actually needs to serve users in their own language, trades the real problem for a worse user experience -- the fix should close the language-specific gap in behavior, not avoid the requirement to support other languages.

## Verify
Re-run the parallel multilingual test set from Diagnose after the fix and confirm failure rates for structured output, instruction-following, and (if applicable) safety guardrail behavior are within an acceptable margin of the English baseline for every supported language, not just improved on average.
