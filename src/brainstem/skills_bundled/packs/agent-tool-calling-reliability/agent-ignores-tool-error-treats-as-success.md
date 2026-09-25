---
name: agent-ignores-tool-error-treats-as-success
description: An agent proceeds as if a failed tool call actually succeeded, building subsequent reasoning and actions on a wrong assumption.
triggers: ["agent didn't notice the tool failed", "agent proceeded after an error", "agent assumed success incorrectly", "silent tool failure downstream", "agent hallucinated a result after failure"]
permissions: ["READ"]
---

## Symptom
A tool call fails (an API error, a timeout, an empty/null result, a
permission denial) but the agent's next turn talks and acts as though it
succeeded -- e.g. it says "I've updated the record" when the update call
actually returned a 403, or it continues a multi-step plan assuming data
was fetched when the fetch errored out. The failure is visible in logs
but invisible in the agent's behavior.

## Likely causes
1. **The tool wrapper swallows the error and returns a default/empty
   value** (`None`, `{}`, `""`) instead of propagating an explicit error
   signal, so from the model's perspective the call "returned
   successfully" with unremarkable-looking data.
2. **The error is returned as data but not distinguished in format from a
   normal successful result** -- e.g. both success and failure come back
   as the same JSON shape with a `message` field, and the model has no
   reliable signal (like a `status` or `error` field) to key off.
3. **The system prompt/tool descriptions never told the model what a
   failure looks like or what to do about it**, so even when an error is
   present in the result, the model wasn't instructed to check for it or
   to treat certain patterns as failures requiring a different response.
4. **Partial success in a batch/multi-item tool call** -- the tool
   returns an overall "200 OK" with a mix of succeeded and failed items
   in a list, and the agent reads the top-level success and never
   inspects the per-item results.
5. **Retries or fallback logic in the tool layer mask an underlying
   failure** (e.g. a cached stale value is returned after a live call
   fails) without flagging that the returned data is degraded.

## Diagnose
- Pull the exact tool-result payload for a known failure case and check
  whether it's structurally distinguishable from a success payload
  (different top-level shape, an explicit `"error"` or `"status": "failed"`
  key) or whether it looks like ordinary data.
- Check the tool wrapper's exception handling path -- does a caught
  exception get converted into a result the model sees, or does it get
  logged and replaced with a default value silently?
- Search the transcript for the agent's own stated reasoning right after
  the failing call -- if it explicitly says something like "the result
  was empty, but I'll assume it worked," that's a prompt/instruction gap;
  if it shows no awareness of anything unusual, that's a signal-design
  gap (the failure wasn't visible in the data at all).
- For batch operations, check whether the tool result includes per-item
  status and whether the agent's instructions say to check each one
  individually rather than trusting an overall success flag.

## Fix
Make failure structurally unmistakable in every tool result, and make
handling it a required step rather than an assumption. Give every tool
result a consistent, explicit status field (e.g. `ok: true/false` or an
`error` key that's present only on failure) so the model doesn't have to
infer failure from the absence or shape of data. Never let a caught
exception in the tool wrapper silently become a default value -- convert
it into an explicit error result with enough detail (what failed, why,
whether it's retryable) for the model to act on correctly. For batch
tools, require the model-facing schema to surface per-item outcomes
(e.g. a list of `{id, status, error?}`) rather than one aggregate flag,
and state in the tool's description that partial failure is possible and
must be checked per item. Where the stakes are high (a destructive or
externally-visible action), add a verification step after the tool call
that independently confirms the claimed effect happened (re-fetch the
record, check the resulting state) rather than trusting the immediate
return value alone.

## Pitfalls
- Adding a status field to the schema but not actually changing the
  handler code to populate it correctly on every failure path -- audit
  every `except`/error branch, not just the happy path, when retrofitting
  this.
- Treating "the tool didn't throw" as equivalent to "the operation
  succeeded" -- many failure modes (empty result set, partial batch
  failure, stale cache fallback) don't throw at all and require explicit
  status signaling, not exception handling.
- Instructing the model in prose to "always check for errors" without
  giving it a reliable structural signal to check -- prompt-only fixes
  degrade under long contexts and complex tasks; the schema-level signal
  is what actually holds up.

## Verify
Force a tool to fail in a controlled test (simulate the API error,
permission denial, or empty result it would return in production) and
confirm the agent's next turn explicitly acknowledges the failure and
changes its plan (retries, reports the failure, or asks for guidance)
rather than proceeding with language or actions that assume success.
