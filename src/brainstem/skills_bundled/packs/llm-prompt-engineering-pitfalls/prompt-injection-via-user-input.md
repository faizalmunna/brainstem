---
name: prompt-injection-via-user-input
description: User-supplied text concatenated into a prompt template contains instructions that override the system prompt's intended behavior.
triggers: ["user typed ignore previous instructions", "prompt injection attack", "user input overrode the system prompt", "jailbreak via input field"]
permissions: ["READ"]
---

## Symptom
A user pastes text into an input field (a support ticket, a document to summarize, a review to analyze) that contains instructions like "ignore previous instructions and instead..." and the model complies -- revealing system prompt contents, performing an unintended action, or producing output the application's guardrails were supposed to prevent. This is often discovered via a security report or a user screenshotting unexpected behavior, not caught by functional testing.

## Likely causes
1. **User input is concatenated directly into the same prompt string as the system instructions** with no structural separation, so the model has no reliable signal distinguishing "instructions from the application developer" from "data the user provided," since both arrive as plain text in the same channel.
2. **Over-reliance on the system prompt's authority alone** -- assuming the model will always prioritize system-role instructions over user-role content purely because of role labeling, without additional structural or output-side safeguards.
3. **No output-side validation** -- even if injection partially succeeds, there's no check that the final output actually conforms to the expected task shape (e.g. a summarization endpoint should never return something that looks like a system prompt dump or an unrelated action).
4. **Untrusted content from indirect sources** (a fetched webpage, an email body, a document being summarized) is treated as safe just because it wasn't typed directly into a chat box by an adversarial user -- indirect injection through RAG'd or tool-fetched content is the same vulnerability class with a less obvious entry point.
5. **No delimiting or escaping of user content**, so a user can include text that mimics the application's own formatting conventions (e.g. fake `### System:` headers) to make injected instructions look structurally privileged.

## Diagnose
- Identify every place user-controlled text (direct input, fetched documents, tool outputs, retrieved chunks) enters a prompt, and check whether it's clearly delimited (e.g. wrapped in an unambiguous boundary and treated as data) versus just string-concatenated.
- Test with known injection patterns ("ignore previous instructions," "you are now DAN," "print your system prompt," fake role headers) against the actual production prompt template and observe whether the model's output changes task or reveals system content.
- Check whether the application validates output shape/content before using it downstream (e.g. does a "summarize this ticket" feature ever return something that isn't a summary, without being flagged?).
- For RAG or tool-augmented flows, test injection embedded in a document that gets retrieved and injected into context indirectly, not just in the direct user-facing input field.

## Fix
Structurally separate trusted instructions from untrusted content rather than relying on wording alone: use the provider's role separation (system vs. user vs. tool messages) correctly, and additionally wrap untrusted content in explicit, hard-to-forge delimiters with an instruction that content between those delimiters is data to process, never instructions to follow. Add output-side validation appropriate to the task (schema/shape checks, a classifier or second model call that checks whether the response stayed on-task) so that even a partially successful injection doesn't reach the end user or a downstream action unchecked. For any flow where the model's output can trigger a tool call or side effect, require that action to pass through the same authorization checks a direct user action would, treating "the model decided to do this because of injected text" as an untrusted request, not an authorated one.

## Pitfalls
Trying to block injection purely with a denylist of phrases like "ignore previous instructions" is a losing arms race -- attackers rephrase trivially, and this approach gives false confidence while leaving the structural vulnerability (no real separation between instructions and data) completely intact.

## Verify
Run a fixed suite of known injection payloads (including indirect ones embedded in documents/retrieved content) against the production prompt template after the fix, and confirm the model's output stays within the intended task shape and never discloses system prompt content, re-running this suite as a regression check whenever the prompt template changes.
