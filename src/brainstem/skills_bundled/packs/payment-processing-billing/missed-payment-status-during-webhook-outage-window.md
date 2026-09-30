---
name: missed-payment-status-during-webhook-outage-window
description: A payment provider's webhook retries for a critical charge or dispute event expire while the receiving endpoint is down during a deploy, permanently losing that status update.
triggers: ["missed webhook during deploy", "payment status never updated", "webhook retries exhausted", "order stuck unpaid after deploy", "chargeback never recorded"]
permissions: ["READ"]
---

## Symptom
An order or subscription is permanently stuck in the wrong state (marked
unpaid when it was actually paid, or vice versa; a dispute/chargeback
never reflected internally) with no error anywhere in your own logs --
because the webhook that would have updated it was never received at all.
Investigation of the provider's dashboard shows the event was sent, all
retry attempts returned connection errors or 5xx, and the provider gave up
after its retry window (commonly 24-72 hours depending on provider) with
no further attempts.

## Likely causes
1. **The webhook endpoint was down or returning 5xx during a deploy** (old
   instances draining, new instances not yet healthy, a load balancer
   briefly routing to nothing) at the exact moment the provider attempted
   delivery, and the deploy's downtime plus the provider's backoff
   schedule happened to exceed the retry window before the endpoint
   recovered.
2. **No reconciliation process exists** to compare the provider's record
   of events/charges against internal state after the fact -- the system
   relies entirely on webhooks arriving, with nothing that periodically
   asks "does the provider have events I never processed?"
3. **The provider's retry backoff is exponential and front-loaded**, so
   most retries happen in the first hour; a deploy-window outage of even
   15-30 minutes can consume most of the early retry attempts, leaving
   only a couple of late, widely-spaced retries before expiry -- teams
   underestimate how much of the retry budget a short outage burns.
4. **Webhook processing failures are not distinguished from delivery
   failures** -- if the endpoint returns 200 but then throws during
   processing (so the event is marked "delivered" by the provider but was
   never actually acted on), the provider won't retry at all because from
   its perspective delivery succeeded, and this looks identical to the
   deploy-outage case in symptom but has a different fix.

## Diagnose
- Check the payment provider's webhook delivery log/dashboard for the
  specific event ID or time range -- it will show every delivery attempt,
  the HTTP status/error for each, and whether retries were exhausted or
  the event is still pending.
- Correlate the failed delivery attempts' timestamps against your deploy
  history/incident timeline -- if the failure window lines up with a
  known deploy, that confirms the outage-during-deploy cause rather than
  an ongoing endpoint problem.
- Check whether your monitoring alerted on the webhook endpoint's error
  rate or downtime at all during the deploy window -- if there's no
  alert, that's a gap independent of this specific incident.
- List all charges/events from the provider's API for the affected date
  range (most providers have a "list events" or "list charges" API, not
  just push webhooks) and diff against your internal records to find
  every other event that may have been silently dropped in the same
  window, not just the one that was reported.

## Fix
Treat webhooks as a low-latency notification mechanism, not the sole
source of truth -- add a periodic reconciliation job that calls the
provider's list/search API for events or charges in a rolling recent
window (e.g. last 24-48 hours) and compares them against internal
records, processing anything missing exactly as the webhook handler would
have. This closes the gap regardless of *why* a webhook was missed (deploy
outage, provider-side bug, network partition) rather than trying to
prevent every possible delivery failure. Separately, make deploys avoid
the outage in the first place: use a deploy strategy with zero-downtime
cutover for the webhook endpoint specifically (health-checked rolling
deploy or blue/green) so there's no window where the endpoint returns
connection errors, and alert immediately (not just via the provider's
dashboard) on a sustained non-2xx rate from the webhook route.

## Pitfalls
- Building the reconciliation job to only check for entirely-missing
  events, without also comparing status/amount fields on events you did
  receive -- a webhook that arrived but was processed with a bug (see
  `duplicate-fulfillment-from-webhook-redelivery`'s inverse: processed
  once but incorrectly) won't be caught by an existence-only diff.
- Making the reconciliation window too short to save on API calls -- if
  it only looks back a few hours but an outage or on-call gap lasts
  longer than that, events can fall through a gap between "webhook
  retries expired" and "reconciliation window starts."
- Relying on manually re-triggering the provider's webhook resend feature
  as the only recovery mechanism -- this requires someone to already know
  something was missed, which defeats the purpose; it's a fine manual
  backstop but not a substitute for automated reconciliation.

## Verify
Simulate the failure by disabling the webhook endpoint (return 503 or
drop connections) for a period longer than a couple of retry attempts
while triggering a test charge/event from the provider's sandbox, confirm
the event shows as failed/exhausted in the provider's dashboard, then run
the reconciliation job and confirm it detects and correctly processes the
missed event without needing the webhook itself to ever arrive.
