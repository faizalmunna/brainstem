---
name: provider-state-mismatch-verifies-against-wrong-data
description: Provider verification reports success but was actually run against the wrong backend data scenario because the provider state setup didn't configure what the interaction expected.
triggers: ["pact provider state not set up correctly", "verification passes but wrong test data", "provider states ignored during verification", "pact test data scenario mismatch"]
permissions: ["READ"]
---

## Symptom

Provider verification for an interaction like "GET /orders/123 given
order 123 exists and is shipped" reports a pass, but the assertion that
actually ran didn't really exercise that scenario -- the provider
returned *some* 200 response (maybe for a default seeded order, or an
empty/mocked response), not specifically the shipped-order-123 case the
interaction's description claims. The contract looks verified, but a
real bug in how the provider handles that specific state (e.g. shipped
orders missing a tracking field) would never have been caught.

## Likely causes

- **The provider state handler for a given state description is missing
  entirely, and the verification framework silently continues** (some
  Pact provider frameworks warn but don't fail when no state handler
  matches a state description), so the request hits whatever data
  already happens to exist rather than data set up specifically for that
  state.
- **The state handler is registered under a slightly different string
  than the state description in the contract** (a typo, different
  wording, or a refactor on one side that wasn't mirrored on the other),
  so matching fails silently and falls through to a default/no-op
  handler.
- **The state handler sets up data but doesn't clean up after the
  previous interaction's state**, so leftover data from an earlier
  provider-state setup (e.g. a previous "order does not exist" state that
  deleted the row) leaks into the next interaction and produces a
  response that happens to satisfy the matcher without the current
  state's setup ever having run.
- **The provider state handler talks to a different data store than the
  one the actual endpoint code reads from** (e.g. seeds a test database
  the handler was written against, while the endpoint under verification
  reads from a cache or a different connection/schema), so the setup
  silently has no effect on what the endpoint actually returns.

## Diagnose

1. Add temporary logging (or check existing verbose verification output)
   inside every provider state handler to print exactly which state
   string it received and confirm it fires for the interaction in
   question -- absence of that log line during the run proves the handler
   never matched.
2. Compare the state description string in the consumer's published pact
   JSON character-for-character against the state handler registration
   in the provider verifier config -- these must match exactly, including
   parameterized values if the framework supports state parameters.
3. Temporarily make the endpoint's real response include the full raw
   data it fetched (not just what the contract checks) during a local
   verification run, and manually confirm it actually reflects the
   scenario the state was supposed to set up, not leftover or default
   data.
4. Check whether provider state setup runs inside a transaction or
   isolated fixture that's rolled back/reset between interactions -- if
   state leaks between interactions run in the same test process, an
   earlier interaction's setup can accidentally satisfy a later one.

## Fix

Make missing or mismatched provider state handlers a hard verification
failure, not a silent no-op -- most Pact provider verification libraries
have a strict mode or equivalent flag for this; enable it. Ensure every
state description used in consumer tests has a corresponding handler
registered with an identical string (consider sharing state description
constants between consumer and provider codebases, or generating them
from a shared schema, if both are in the same monorepo) and that each
handler performs setup and teardown against the exact same data
store/connection the running endpoint uses, wrapped in a transaction or
reset routine that guarantees isolation between interactions.

## Pitfalls

Don't make provider state handlers overly generic (a single handler that
tries to interpret many different state strings via string matching or
regex) as a shortcut to avoid registering each one explicitly -- that
reintroduces the same silent-mismatch risk one level up, since a typo'd
state string can still accidentally match a broad pattern and produce
plausible-looking but wrong data. Prefer exact, explicit registration per
state, even if it's more verbose.

## Verify

Deliberately misspell a provider state description in the consumer
contract (simulate the mismatch) and confirm the provider verification
run now fails loudly with an explicit "no handler found for state" error
rather than passing silently. Then fix it back and re-run verification
with logging enabled, confirming each interaction's log output shows the
exact state handler that fired and the specific data it set up
immediately before that interaction's request was made.
