---
name: unvalidated-tool-output-propagates-downstream
description: A tool's returned data isn't validated against its own declared output schema, so a malformed response silently corrupts later agent reasoning.
triggers: ["tool returned unexpected shape", "downstream code broke from bad tool output", "malformed API response fed to agent", "tool output schema not enforced", "silent data corruption from tool call"]
permissions: ["READ"]
---

## Symptom
A tool call succeeds (no exception, no error status) but returns data
that's missing an expected field, has a subtly wrong type, or comes from
an upstream API that changed its response shape -- and this bad shape
flows straight into the agent's context and any downstream code that
parses the result, causing wrong reasoning, a crash several steps later
in an unrelated-looking place, or a value silently coerced to something
incorrect (e.g. `undefined` printed as the literal string `"undefined"`
and treated as real data).

## Likely causes
1. **The tool has a declared output schema (in its definition, or
   implicitly in code comments/types) that's never actually checked at
   runtime** -- it exists as documentation for the model but nothing
   enforces that the real returned data matches it before use.
2. **The tool wraps a third-party API whose response shape isn't fully
   controlled** -- a field gets renamed, deprecated, or becomes
   optional upstream, and the wrapper keeps assuming the old shape.
3. **Partial/degraded responses look structurally valid** -- e.g. a
   paginated API returns an empty `items: []` array on a transient
   backend error rather than an explicit error status, and both "no
   results" and "request failed" look identical to downstream code.
4. **Type coercion happens implicitly in a dynamically-typed language**
   -- a missing field becomes `null`/`undefined`/`None` and gets passed
   along through several layers before something finally fails (or
   worse, silently produces a wrong-but-plausible result) far from the
   actual root cause.
5. **The agent framework only validates the tool *call* (arguments going
   in) but has no symmetric validation for the tool *result* (data
   coming out)**, treating input and output as asymmetric concerns when
   both need the same rigor.

## Diagnose
- Check whether the tool's output schema (if one is declared) is
  actually enforced anywhere in code, or whether it's purely descriptive
  metadata shown to the model with no runtime check.
- Reproduce the failure and trace backward from where the error/wrong
  behavior actually surfaced to the original tool call that produced the
  malformed data -- the distance between cause and symptom is usually
  the main diagnostic difficulty here, so add logging of raw tool output
  at the source, not just at the point of failure.
- For tools wrapping external APIs, check the provider's changelog/status
  page for recent response-shape changes, and compare a fresh live call's
  actual response against the shape the wrapper code assumes.
- Check whether "no results" and "error" are actually distinguishable in
  the tool's current output, or whether both produce the same-looking
  empty/default value.

## Fix
Validate tool output against its declared schema at the same boundary
where you validate tool input, immediately after the underlying call
returns and before the result is handed to the model or to any
downstream code. Use the same schema definition for both generating the
tool's advertised output contract and for runtime validation, so the two
can't drift apart. On a validation failure, don't let the bad data
propagate with a best-effort partial parse -- surface it as an explicit
tool-level error (distinct from a normal empty/successful result) so the
agent (or a human-facing error path) can react to "this tool is
returning bad data" rather than reasoning over corrupted values. For
tools wrapping third-party APIs prone to drift, add a lightweight
contract check (verify a couple of required fields exist with the
expected type) as a fast-fail guard specifically for that fragility,
separate from general application error handling.

## Pitfalls
- Validating only the top-level shape (e.g. "is this valid JSON") without
  checking the actual field-level schema (types, required fields) --
  this catches transport-level corruption but misses the much more
  common case of a structurally valid but semantically wrong response.
- Treating a caught validation error the same as a caught network error
  and retrying blindly -- a schema mismatch from an upstream API change
  won't be fixed by retrying and will just burn calls; distinguish
  transient failures (retry) from structural mismatches (needs a code/
  schema fix) in the error handling.
- Adding output validation but only logging the failure rather than
  actually blocking the bad data from reaching the model -- a logged-but-
  ignored validation error provides observability without providing the
  actual reliability improvement.

## Verify
Feed the tool's handler a deliberately malformed response (missing a
required field, wrong type on one field, matching a known real-world
drift scenario if you have one) in a test, and confirm the validation
layer catches it and produces an explicit error result rather than
letting it reach the agent's context or downstream parsing code
unflagged.
