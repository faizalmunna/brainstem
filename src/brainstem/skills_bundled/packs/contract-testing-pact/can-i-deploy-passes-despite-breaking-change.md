---
name: can-i-deploy-passes-despite-breaking-change
description: The can-i-deploy compatibility check approves a release even though the provider added a new required field or removed one the consumer depends on.
triggers: ["can-i-deploy said yes but broke consumer", "breaking change shipped despite contract check passing", "pact matrix green but new required field broke client", "provider added required field and consumer didn't catch it"]
permissions: ["READ"]
---

## Symptom

The provider team adds a new required request field, renames a response
field, or removes a field a consumer was reading, and the CI/CD pipeline's
`can-i-deploy` (or equivalent compatibility gate) still says it's safe to
deploy. The change ships and breaks the consumer immediately. Reviewing
the pact matrix afterward shows verification technically "passed" --
because the contract itself was never updated to encode the new
requirement, so there was nothing for verification to check.

## Likely causes

- **The breaking change was made only on the provider side, and no
  consumer test was updated to express the new requirement**, so the
  existing published contract still reflects the old shape; verification
  against an unchanged, already-satisfied contract trivially passes
  regardless of what else the provider now requires.
- **The new required field was added with a default value on the
  provider's own test/verification requests but not documented as
  actually required for real traffic**, so the provider's own tests pass
  even though real consumer requests (which don't send the new field)
  would be rejected in production.
- **The removed/renamed field was optional in the contract's matcher
  (`like`) so its absence doesn't fail verification**, even though the
  consumer's actual code unconditionally reads that field and will throw
  or silently misbehave (e.g. `undefined` propagating downstream) when
  it's missing.
- **`can-i-deploy` was checked against a stale or wrong consumer version**
  (see the version-tagging pitfalls in this pack) so even if the contract
  had been updated correctly, the gate wasn't evaluating the version
  actually being deployed.

## Diagnose

1. Diff the provider's request/response schema before and after the
   breaking change against the exact contract JSON currently published by
   the consumer -- confirm explicitly whether the changed field appears
   in the contract at all, and with what matcher/requirement.
2. Check whether the provider's own integration/unit tests for the new
   required field pass only because the test harness supplies the field
   by default (e.g. a shared fixture), which would mask the fact that
   real, unmodified consumer requests omit it.
3. Trace the consumer's actual usage of the removed/renamed field in its
   codebase -- grep for the field name in the consumer's HTTP client/
   response-handling code to confirm it's actually read and what happens
   when it's absent (exception vs. silently undefined vs. genuinely
   unused dead code).
4. Confirm this is a genuine contract gap and not a broker-matrix mistake
   by re-running `can-i-deploy` locally against the exact consumer and
   provider versions involved in the incident, and read the full output
   rather than just the pass/fail exit code.

## Fix

Treat a breaking provider change as requiring a corresponding consumer
contract update *before* the provider change is considered mergeable --
in practice, this means the provider team should coordinate with (or
directly open a PR against) the consumer's pact tests to add the new
required field or remove the deprecated one, get that contract published,
and only then let verification run against the new provider behavior.
For fields going away, use a deprecation window: keep the field present
(possibly with a marker or a lowered guarantee) until the pact broker's
matrix shows every currently-deployed consumer version's contract has
been updated to no longer depend on it, confirmed via `can-i-deploy`
for the specific removal version against all real consumer deployments,
not just the latest one.

## Pitfalls

Don't let the provider team treat "my own tests pass" as sufficient
evidence of safety for a shared contract -- the entire point of consumer-
driven contracts is that the consumer's actual expectations, not the
provider's assumptions about them, are what gets verified. Also don't
add the new required field to the contract's matcher as optional
(`like` on a field that's actually mandatory) just to make verification
pass quickly -- that re-creates the same gap this skill is about,
just one level removed.

## Verify

Update the consumer's pact test to explicitly require the new field (or
explicitly assert the removed field's absence doesn't break consumer
logic), publish the updated contract, and confirm provider verification
now fails against the *old* provider code that doesn't yet send the new
field -- proving the contract actually encodes the requirement. Then
deploy the provider's real fix and confirm `can-i-deploy` passes only
after both the contract update and the provider change are in place, not
before.
