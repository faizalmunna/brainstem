---
name: tool-result-floods-context-window
description: A single tool call returns so much raw data that it floods the agent's context window, causing it to lose track of earlier instructions or hit token limits.
triggers: ["tool response too large", "context window exceeded after tool call", "agent forgot earlier instructions", "context overflow from search results", "truncated tool output breaking agent"]
permissions: ["READ"]
---

## Symptom
After a tool call (a file read, a database query, a web search, a log
fetch) returns a large payload, the agent's subsequent responses degrade
-- it stops following system-prompt instructions given earlier, forgets
task constraints stated at the start of the conversation, or the request
outright fails with a context-length error. This often only surfaces on
certain inputs (a big file, a query that happens to match many rows),
making it look intermittent.

## Likely causes
1. **The tool has no output size cap** -- it returns the entire result set
   (full file contents, all rows, entire API response) regardless of
   size, trusting the model to handle whatever comes back.
2. **No summarization or pagination layer between the raw data source and
   the tool result returned to the model** -- the tool was built as a
   thin passthrough to an underlying API/DB/filesystem without
   considering that "return everything" doesn't compose with a bounded
   context window.
3. **Important instructions live too early in a long-running
   conversation** -- even without hitting the hard token limit, models
   attend less reliably to instructions buried far before a large
   intervening block of tool output ("lost in the middle"), so a big
   tool result pushes critical context effectively out of reach even
   though it's technically still in the window.
4. **Repeated large tool calls accumulate across turns** -- no single call
   is oversized, but the agent calls a moderately large tool many times
   in one session and nothing evicts or summarizes earlier results, so
   the cumulative context grows unbounded.
5. **Tool output includes redundant/verbose formatting** (pretty-printed
   JSON with whitespace, HTML markup, repeated boilerplate headers) that
   inflates token count well beyond the information actually needed.

## Diagnose
- Log token counts per tool result (not just the final prompt token
  count) to identify which specific tool calls are the outliers.
- Reproduce the failure with the exact input that triggered it and check
  whether the result size correlates with input size unboundedly (e.g.
  linear in number of matching rows) versus being capped.
- If instructions are being "forgotten" without a hard context-limit
  error, check where in the conversation those instructions sit relative
  to the large tool result -- confirm the lost-in-the-middle pattern by
  testing whether the same instruction is followed correctly when it's
  the most recent message versus buried before a large block.
- Check whether the tool's underlying data source supports native
  pagination/limiting (`LIMIT`, cursor, `max_results`) that the tool
  wrapper simply isn't using.

## Fix
Design every tool that can return unbounded data with a hard cap and a
summarization/pagination strategy, not just a "hope it's small" default.
Concretely: enforce a max result size (rows, characters, or bytes) at the
tool boundary and return a truncated result plus an explicit signal that
more data exists and how to fetch the next page/refine the query, so the
model can decide whether it needs more rather than silently getting a cut
result it thinks is complete. For tools whose natural output is very
large (full file contents, long logs), offer a summarized or filtered
view by default (e.g. return matching lines with context instead of the
whole file, or a schema/sample instead of every row) and a separate,
explicit "get more/get full" action for when the agent actually needs
it. For long sessions, periodically compact or summarize older tool
results out of the live context (replacing them with a short summary)
once they're no longer immediately relevant, and re-state critical
constraints close to the point where the model needs to act on them
rather than relying on them surviving from far earlier in the
conversation.

## Pitfalls
- Truncating a large result silently (just cutting the string at N
  characters) without telling the model it was truncated -- the model
  then reasons over partial data believing it's complete, which is worse
  than an explicit size limit error.
- Over-correcting by making every tool return tiny summaries by default,
  forcing the agent into many extra round trips to get data it needed
  anyway -- calibrate the default page/result size to the tool's typical
  use case instead of an arbitrary small constant.
- Compacting/summarizing old tool results using the same model mid-task
  without preserving the specific facts later steps depend on --
  summarization itself can drop the one detail (an ID, a exact value)
  a later step needed.

## Verify
Trigger the tool with an input known to produce a large result (a big
file, a broad query) and confirm: the tool result comes back under the
configured size cap, includes an explicit "truncated, N more available"
indicator when applicable, and a follow-up turn correctly still follows
an instruction stated earlier in the conversation -- check this
specifically, not just that the run completes without a token-limit
error.
