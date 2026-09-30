---
name: tool-call-argument-schema-mismatch
description: A model-generated tool call has the wrong argument type, a missing required field, or extra fields the tool's schema doesn't declare.
triggers: ["tool call missing required field", "wrong type in tool arguments", "schema validation error on tool call", "model passed a string instead of a number", "malformed function call arguments"]
permissions: ["READ"]
---

## Symptom
A tool call parses as valid JSON but fails validation against the tool's
own parameter schema -- a required field is absent, a number arrives as
a string (`"5"` instead of `5`), an enum field gets a value outside the
allowed set, or the model invents an extra field the tool doesn't
recognize. This happens intermittently, not on every call to that tool,
which rules out a broken integration and points at the model's
generation being unreliable for that specific schema.

## Likely causes
1. **The tool's parameter descriptions are ambiguous or missing units/
   format hints** -- a field named `date` with no format spec gets
   `"next Tuesday"` from the model instead of an ISO date, because
   nothing in the schema told it which format to produce.
2. **The schema declares a field as optional when the tool's actual
   runtime behavior requires it** (or vice versa) -- the model correctly
   omits an "optional" field per the schema, but the handler assumes
   it's always present and fails downstream instead of at the boundary.
3. **Overly complex nested schemas** (deeply nested objects, arrays of
   unions, mutually-exclusive field groups) exceed what the model
   reliably produces in one shot -- structured generation degrades as
   schema complexity grows, especially for smaller/faster models used to
   keep latency down.
4. **The schema changed (field renamed, type tightened) but few-shot
   examples, cached system prompts, or model context from earlier in a
   long conversation still reflect the old shape**, so the model
   pattern-matches to stale examples.
5. **No coercion/normalization layer** -- the tool handler expects exact
   types and rejects a value that's semantically fine but structurally
   off (e.g. `"5"` for an integer field) instead of normalizing it.

## Diagnose
- Turn on schema validation logging that records the raw arguments object
  alongside the specific validation failure (field, expected type, actual
  value) -- don't just log "invalid arguments," log the diff.
- Look for a pattern across failures: same field failing repeatedly
  suggests a schema/description problem; scattered random fields failing
  occasionally suggests general format-following weakness under load
  (long context, high schema complexity) rather than one bad field.
- Test the tool's schema in isolation with a handful of representative
  prompts and check how consistently the model produces valid calls
  outside the full agent loop -- this isolates whether the schema itself
  is the problem versus something upstream (truncated context, confusing
  system prompt) corrupting an otherwise-fine schema.
- Check whether the field that fails validation has an ambiguous name or
  no `description`/`enum`/`format` constraint in the schema definition.

## Fix
Treat the tool schema itself as the primary lever, not just a validation
gate after the fact. Add explicit format hints to every field description
(units, exact format like `YYYY-MM-DD`, valid enum values spelled out,
one example value) -- models follow schemas far more reliably when the
description removes ambiguity rather than relying on the type alone.
Flatten deeply nested or union-heavy schemas into simpler, flatter shapes
where possible, or split one complex tool into two simpler ones. At the
validation boundary, add a coercion step for cheap, unambiguous
mismatches (numeric strings to numbers, trimming whitespace) before
rejecting outright, and when validation does fail, return a tool-result
error that states exactly which field failed and why (not a generic
"invalid arguments") so the model's retry has a real chance of succeeding
based on that feedback.

## Pitfalls
- Silently coercing values that are actually ambiguous (e.g. guessing a
  date format) instead of only coercing genuinely unambiguous cases --
  this can turn a loud, catchable error into a quiet wrong-data bug.
  Coerce only when the source and target are provably equivalent.
- Adding more free-text instructions in the system prompt telling the
  model "always format dates as ISO" instead of fixing the schema itself
  -- schema-level constraints (enums, format annotations, JSON Schema
  patterns) are far more reliable than prose instructions repeated in the
  prompt, which compete with everything else in context.
- Rejecting on the first validation failure without ever surfacing which
  field/value failed to the model -- forces blind retries that often
  reproduce the same mistake.

## Verify
Collect a sample of real failing tool calls, apply the improved schema
descriptions (and any coercion rules) without touching the model, and
replay the same prompts to confirm the failure rate for that tool drops
measurably -- track a before/after invalid-call rate per tool, not just
"it seems better."
