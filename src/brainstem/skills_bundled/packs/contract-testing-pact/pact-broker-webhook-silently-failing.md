---
name: pact-broker-webhook-silently-failing
description: Pact broker webhooks meant to trigger provider verification stop firing successfully after a URL, credential, or CI system change, and nobody notices until an untested contract change ships.
triggers: ["pact webhook stopped triggering ci build", "provider verification never runs automatically anymore", "pact broker webhook returning error", "contract published but no ci job started"]
permissions: ["READ"]
---

## Symptom

Provider verification used to run automatically whenever a consumer
published a new or changed contract, but at some point it quietly
stopped -- consumers keep publishing pacts, but no corresponding CI run
appears on the provider side, and nobody notices for days or weeks
because the absence of a build doesn't page anyone the way a failing
build would. This is distinct from a webhook that was never configured
(a one-time setup gap) -- here it worked before and broke silently after
some unrelated change.

## Likely causes

- **The CI system's webhook-triggered endpoint or API token changed**
  (a CI provider migration, a rotated personal access token, a renamed
  pipeline/project) and the Pact Broker's webhook configuration was never
  updated to match, so every delivery now fails with an auth error or 404
  that nobody is watching for.
- **The provider's CI trigger endpoint added new required parameters or
  changed its expected payload shape**, so the webhook fires and gets a
  response, but the response is a 4xx the broker logs as a failed
  delivery rather than a 2xx, and nobody reviews webhook delivery logs
  as a matter of routine.
- **A firewall, VPN, or network policy change blocks the Pact Broker
  (self-hosted or Pactflow) from reaching the CI system's webhook URL**,
  especially after infrastructure migrations or tightened egress/ingress
  rules, causing deliveries to time out rather than fail fast with a
  clear error.
- **The webhook exists and fires successfully, but for the wrong
  event trigger** (e.g. it was reconfigured to fire only on
  `provider_verification_published` instead of `contract_content_
  changed`), so it technically "works" but never actually runs on the
  event that matters.

## Diagnose

1. In the Pact Broker UI (or API), open the webhook's delivery history
   for the consumer/provider pair in question and check the most recent
   delivery attempts' HTTP status codes and response bodies -- this
   directly shows whether it's firing, and why it's failing if so.
2. Use the broker's "redeliver" or "test this webhook" action to trigger
   it manually right now and observe the live result, rather than relying
   only on historical logs which may reflect an already-fixed or
   already-worse state.
3. Check the CI system's own audit/access logs for incoming webhook
   requests around the time of a manual test -- if the CI system shows no
   incoming request at all, the problem is network/connectivity between
   broker and CI; if it shows a rejected request, the problem is
   auth/payload format.
4. Diff the webhook's configured event type and URL against what's
   documented (or against a known-working sibling consumer/provider pair
   in the same broker instance) to catch a misconfiguration that isn't
   an outright failure.

## Fix

Configure webhook failure notifications rather than relying on someone to
notice a build didn't run -- most Pact Broker setups support notifying a
Slack channel or email on webhook delivery failure; wire this up so a
broken webhook pages a human within one failed delivery, not after weeks
of silent gaps. When fixing the specific break, update the stored
URL/credentials to match the current CI system's actual trigger endpoint
and authentication method, and re-test with a real "redeliver" action
against a real recent contract change rather than trusting the
configuration change alone. Where feasible, add a low-frequency
reconciliation check (e.g. a scheduled job comparing "contracts published
in the last N days" against "provider verification runs in the last N
days") as a backstop independent of the webhook mechanism itself.

## Pitfalls

Don't treat a successful manual "test webhook" click as sufficient proof
it's fixed -- the test payload some broker UIs send can differ from a
real contract-publish payload, and it's possible for the test action to
succeed while the real event trigger remains misconfigured. Verify
against an actual contract publish, not just the UI's synthetic test
button. Also don't quietly fix the webhook and move on without checking
how long it had been broken -- audit whether any consumer contracts
published during the outage window were ever actually verified, since
those are exactly the un-verified changes this skill's failure mode is
about.

## Verify

Publish a real, deliberately-changed contract from the consumer's test
suite and confirm, within the pipeline's normal latency, that a
corresponding provider CI run starts automatically and its result is
recorded back to the broker against the correct consumer version --
without any manual trigger. Then confirm the failure-notification path
works too, by temporarily pointing the webhook at an invalid URL and
checking that the configured alert actually fires before restoring the
correct configuration.
