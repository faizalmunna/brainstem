---
name: new-provider-endpoint-never-gets-verified
description: A consumer starts calling a newly added provider endpoint but no contract test or verification ever runs against it, so integration bugs ship undetected.
triggers: ["new endpoint not covered by contract tests", "pact broker webhook never triggered provider build", "consumer added new api call with no pact verification", "contract testing didn't catch new endpoint break"]
permissions: ["READ"]
---

## Symptom

A consumer team adds a call to a provider endpoint that's new to their
integration (either a brand-new provider route, or an existing route
they hadn't used before), ships it, and it breaks in a downstream
environment. Looking back, there was never a provider verification run
that covered this endpoint at all -- not a failure, an absence. The pact
broker shows no pending or failed verification for it; the interaction
simply never triggered anything on the provider side.

## Likely causes

- **The Pact Broker webhook that triggers the provider's verification
  build on contract publish isn't configured (or is misconfigured)** for
  this consumer/provider pair, so publishing a new contract version never
  actually kicks off CI on the provider side -- verification only runs
  whenever someone happens to trigger the provider pipeline manually.
- **The provider's verification step filters interactions by tag or
  provider state and the new endpoint's interaction doesn't match any
  configured filter**, so it's silently skipped even though verification
  otherwise runs and reports green.
- **The consumer test suite never actually wrote a pact interaction for
  the new endpoint** -- the code calls it, but no consumer-side contract
  test exists for that call, so there's nothing in the published contract
  for the provider to verify against in the first place.
- **The provider verification job pins to a specific pact tag/branch
  (e.g. only verifies contracts tagged `main`)** and the new interaction
  was published from a feature branch or under a different tag that the
  verification job's selector doesn't include.

## Diagnose

1. In the Pact Broker, look up the consumer's published contract and
   confirm whether an interaction for the new endpoint actually exists in
   it -- if it's missing entirely, the gap is on the consumer test side,
   not the webhook.
2. If the interaction exists, check the broker's webhook configuration
   for this consumer/provider pair (`pact-broker webhook` list or the UI)
   and confirm a "contract content changed" webhook is registered and
   points at a working CI trigger URL -- test it directly with the
   broker's "test webhook" action and check for a non-2xx response or
   auth failure.
3. Check the provider's verification invocation (e.g.
   `pact_broker_base_url` + selectors/consumer version selectors in the
   verifier config) for a filter that excludes this contract by tag,
   branch, or `WIP` pact settings -- confirm the exact selector logic
   being used, since a narrow selector will silently exclude new
   contracts that don't match it.
4. Check CI history for the provider repo around the time the consumer
   published -- if there's no corresponding verification run at all, the
   trigger chain is broken; if there's a run that reports zero
   interactions verified, the selector/filter is excluding it.

## Fix

Make the contract-publish-to-verification path fully automated and
observable: configure the Pact Broker webhook to fire the provider's CI
pipeline on every contract content change for that consumer, using the
broker's built-in webhook templates so the payload includes enough
context (consumer name, version) for the provider job to fetch and
verify the right contract. Configure the provider's verifier to use
broad-enough consumer version selectors (e.g. "all currently deployed and
released" plus the main branch) so new interactions aren't excluded by
an overly narrow tag filter, and enable `WIP` (work-in-progress) pact
support so brand-new consumer interactions surface as non-blocking
warnings on the provider side immediately, rather than waiting for a
separate release process to notice them.

## Pitfalls

Don't rely on someone remembering to manually trigger the provider build
whenever a consumer adds a new call -- that "remember to tell the other
team" step is exactly what contract testing automation exists to remove,
and it will eventually be forgotten. Also don't respond to a missed
webhook by making the provider pipeline poll the broker on a timer as
the primary mechanism -- polling adds latency and still needs the
webhook (or an equivalent event trigger) to be the real detection path;
use polling only as a redundant safety net, not the main trigger.

## Verify

Add a genuinely new interaction to the consumer's pact test, publish it,
and watch the Pact Broker webhook log to confirm it fired and returned a
2xx response, then confirm a corresponding provider CI run appears
automatically (not manually triggered) and its verification output
explicitly lists the new interaction as checked, with a pass/fail result
recorded back to the broker for that consumer version.
