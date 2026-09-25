---
name: hallucinated-tool-call-crashes-agent
description: An LLM agent emits a tool call naming a function that doesn't exist or a plausible-but-wrong parameter, and the app hard-crashes instead of recovering.
triggers: ["agent called a tool that doesn't exist", "unknown function name from model", "KeyError on tool dispatch", "model hallucinated a tool", "agent crashed on invalid tool call"]
permissions: ["READ"]
---

## Symptom
The agent's tool-calling loop throws an unhandled exception (`KeyError`,
`AttributeError`, a dispatcher `else: raise`) because the model requested
a tool name that was never registered, or requested a real tool with a
parameter name that looks right but doesn't match the schema (e.g.
`filepath` instead of `file_path`). The whole run dies instead of the
agent getting a chance to self-correct.

## Likely causes
1. **The tool dispatcher does direct dictionary/attribute lookup on the
   model's tool name with no existence check** -- `tools[call.name](...)`
   throws `KeyError` immediately rather than checking membership first.
2. **The model is inferring tool names/params from training-data patterns**
   (e.g. it has seen thousands of `get_user(user_id)` signatures and
   invents one for a tool that's actually named differently) because the
   tool list wasn't in the model's context at generation time, or the
   tool was recently renamed and old few-shot examples/cached prompts
   still reference the old name.
3. **Tool definitions were silently dropped or truncated** -- a context-
   window trim, a bug in how the tool list is serialized, or a
   feature-flagged subset of tools shown to the model -- so the model
   is choosing from a stale mental list of tools it saw earlier in a
   long conversation but which are no longer actually registered.
4. **No schema validation layer between "model produced JSON" and
   "application calls a function with it"** -- the app trusts the model's
   output shape completely and unpacks it directly into a function call.

## Diagnose
- Log every raw tool-call payload (name + raw arguments) before any
  dispatch logic touches it, and check the log for the exact failing
  call -- confirm whether the name is *close to* a real tool (likely
  hallucination/drift) or wildly unrelated (likely a context/prompt bug).
- Diff the tool list actually sent in the API request payload for that
  turn against the tool registry the dispatcher uses -- if they differ,
  it's a registration/serialization bug, not a model failure.
- Check conversation length/turn count when the crash happens -- if
  failures cluster late in long sessions, suspect context truncation
  dropping tool definitions or earlier tool-result messages that
  anchored correct tool names.
- Grep recent commits/config for tool renames and check whether cached
  prompts, few-shot examples, or system-prompt text still reference the
  old name.

## Fix
Treat every tool call from the model as untrusted input, the same way
you'd treat a request body from an external client. Put a validation
layer between "model output" and "function invocation": look up the tool
name against the live registry first and, on a miss, don't crash -- return
a tool-result message (in the same tool-result format the model expects,
with the matching call ID) stating the tool doesn't exist and, ideally,
listing the closest valid names. This turns a fatal error into a normal
turn the model can react to, because from the model's perspective an
"error: no such tool" result is just more conversation context it was
trained to handle. Apply the same pattern to per-tool argument validation
(see the argument-schema-mismatch skill in this pack) rather than only
checking the top-level name.

## Pitfalls
- Catching the exception but returning an empty/silent success instead of
  an explicit error result -- the agent then proceeds believing the
  (nonexistent) tool worked, which is worse than a crash because the
  failure becomes silent and downstream (see the silent-tool-failure
  skill in this pack).
- Fixing this only at the top-level try/except around the whole agent
  loop -- that stops the crash but loses the turn's context and typically
  forces a full restart; the fix belongs at the dispatch boundary so only
  that one tool call fails, not the whole run.
- Auto-retrying the hallucinated call verbatim without feeding back *why*
  it failed -- the model will often repeat the exact same wrong call
  because it has no new information to correct itself with.

## Verify
Manually inject a tool call in a test with a name that isn't registered
(and separately, a registered name with a misspelled parameter key) and
confirm the loop continues, produces a structured error tool-result
instead of raising, and the agent's next turn shows it choosing a
different (correct) tool or asking for clarification -- not repeating the
identical invalid call.
