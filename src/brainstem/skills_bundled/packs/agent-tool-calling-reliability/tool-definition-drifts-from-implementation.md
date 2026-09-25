---
name: tool-definition-drifts-from-implementation
description: A tool's schema and description shown to the model no longer match what the underlying function actually accepts or does after a code change.
triggers: ["tool schema out of sync with code", "tool works differently than documented to the model", "agent using outdated tool description", "tool definition drift after refactor", "model calling deprecated tool parameters"]
permissions: ["READ"]
---

## Symptom
A tool call that matches its documented schema exactly still fails, or
succeeds but does something different than the model (and the developer
reading the tool description) would expect -- because the underlying
function was refactored, a parameter's meaning changed, a default
changed, or a side effect was added or removed, while the schema/
description string shown to the model was never updated to match. This
is distinct from the model producing a malformed call: the call is
well-formed by the documented contract, the contract itself is stale.

## Likely causes
1. **The tool schema is hand-maintained as a separate JSON/dict literal
   from the actual function signature**, so a developer changes the
   function during a refactor and has no compiler/linter forcing the
   schema to be updated in lockstep.
2. **A parameter's accepted values or semantics changed silently** (e.g.
   a `status` enum gained a new value, or a boolean flag's default
   flipped) as part of an unrelated feature change, without anyone
   auditing which tool descriptions reference that parameter.
3. **No automated test asserts that the tool schema matches the function
   it wraps** -- schema/implementation parity is treated as a
   documentation concern rather than a correctness invariant with test
   coverage.
4. **The tool wraps a versioned external API and the wrapper was upgraded
   to a new API version** whose request/response shape differs, but the
   tool description shown to the model still reflects the old version's
   behavior.
5. **Multiple tool definitions reference shared helper functions or
   constants that changed**, and updating the helper doesn't visibly
   touch the tool definition files, so the drift is easy to miss in code
   review.

## Diagnose
- Pick a tool and manually diff its declared schema/description against
  the actual function signature and docstring/behavior in code --
  literally read both side by side; drift is often obvious once you
  look, but nothing prompts anyone to look.
- Check whether there's any test that calls the tool with schema-valid
  example inputs and asserts the real function accepts and processes
  them as described -- absence of such a test is itself the root cause,
  not just a diagnostic gap.
- Search recent commit history for changes to the function a tool wraps
  and check whether the corresponding tool definition file was touched
  in the same commit or PR -- a function change with no matching schema
  change is a strong drift signal.
- Look for support/bug reports where the agent's behavior technically
  matched the tool's documented contract but a human still calls it
  "wrong" -- that gap between "matches the doc" and "matches what we
  actually wanted" is the signature of this issue versus a plain
  malformed-call bug.

## Fix
Generate the tool schema from the actual function signature/type
annotations wherever the language and framework support it, rather than
hand-maintaining a parallel description -- this makes drift structurally
impossible for parameter names and types (though not for prose semantics,
which still needs discipline). Where full generation isn't feasible, add
a contract test per tool that invokes the real underlying function with
each example value implied by the schema (including enum values, edge
cases like `null`/optional fields) and asserts it behaves as the
description claims, so schema/implementation drift fails CI instead of
surfacing as a production behavior mismatch. Require that any PR
changing a function's signature or semantics that's exposed as a tool
also touches the tool definition in the same diff, and make this
checkable via a lint rule or code-owner rule tying the two files
together where automatic generation isn't available.

## Pitfalls
- Auto-generating the schema's types/required-fields from code but
  leaving the human-written prose description stale -- type-level drift
  gets fixed while semantic drift (what a parameter *means*, when to use
  the tool) persists silently, since generation typically can't capture
  intent.
- Writing a contract test that only checks the schema *validates*
  example inputs (a JSON Schema check) without ever calling the real
  function, which catches shape drift but not behavioral drift (same
  shape, different effect).
- Treating this as a one-time cleanup pass rather than an ongoing
  invariant -- without a structural safeguard (generation or CI contract
  test), the same drift reappears after the next unrelated refactor.

## Verify
For the tool in question, run its documented example inputs (one per
enum value or meaningfully distinct case in the schema) against the live
function and confirm both the acceptance (no unexpected rejection) and
the actual behavior/output match what the tool's description promises a
model-driven caller should expect -- then add this as a standing
automated test so future refactors fail loudly instead of drifting
again.
