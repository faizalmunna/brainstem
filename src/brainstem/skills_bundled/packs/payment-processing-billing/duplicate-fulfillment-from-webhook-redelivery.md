---
name: duplicate-fulfillment-from-webhook-redelivery
description: A payment provider redelivers the same charge-succeeded webhook event more than once and the handler fulfills the order or grants entitlements again each time.
triggers: ["webhook fired twice", "order fulfilled twice", "duplicate webhook event", "stripe webhook sent multiple times", "customer got two confirmation emails"]
permissions: ["READ"]
---

## Symptom
The same order gets fulfilled twice (two shipment records, two license
keys issued, two "your subscription is active" emails), or an internal
balance/credit is incremented twice, and investigation shows the payment
provider's dashboard logs the *same* event ID being delivered to your
webhook endpoint on two or more separate occasions. This is different
from `duplicate-charge-from-retried-payment-request`: here there is only
one real charge at the processor, but your system reacted to the
notification about it more than once.

## Likely causes
1. **The webhook handler has no dedup check against the event ID at all**
   -- every provider (Stripe, PayPal, Adyen, Braintree, etc.) documents
   at-least-once delivery and explicitly recommends storing processed
   event IDs, but many handlers are written assuming exactly-once and just
   process whatever payload arrives.
2. **The handler does real work before acknowledging (returning 200)**,
   so if fulfillment is slow and the provider's timeout fires first, the
   provider marks the delivery as failed and retries -- even though your
   handler actually finished successfully the first time.
3. **Dedup is checked and recorded as two non-atomic steps** ("has this
   event ID been seen? no -> process -> mark as seen"), so two near-
   simultaneous deliveries of the same event both pass the "not seen yet"
   check before either finishes recording it, both proceeding to fulfill.
4. **Signature verification or parsing failure causes a non-2xx response
   for a validly-processed event** (e.g. clock skew rejecting the
   timestamp, or an unhandled event subtype throwing an exception after
   the important side effect already ran), causing the provider to retry
   an event that already had its effect applied.

## Diagnose
- Query the provider's webhook event log/dashboard for the order in
  question and count how many delivery attempts were made for that event
  ID, and what HTTP status your endpoint returned on each attempt.
- Check your own webhook handler's logs for the event ID appearing more
  than once, and note the response code and latency of each -- a pattern
  of "200 returned, but slowly" followed by a retry indicates the timeout-
  before-ack problem; a pattern of "non-2xx returned" indicates a
  signature/parsing/exception issue triggering legitimate retries of an
  event that already succeeded.
- Check whether a `processed_webhook_events` (or equivalent) table/set
  exists at all, and if it does, whether the insert happens before or
  after the fulfillment side effect, and whether the insert has a unique
  constraint.

## Fix
Persist every successfully-handled event ID in a dedup store (a database
table with a unique constraint on `event_id`, or equivalent) and make the
"insert the event ID" step atomic with -- and prior to -- the decision to
proceed, using the unique constraint itself as the concurrency guard: `INSERT
... ON CONFLICT DO NOTHING`-style logic where a conflict means "already
processed, return success and stop," not two separate check-then-act
calls. Acknowledge the webhook (return 2xx) as soon as the event is durably
queued or the essential state change is committed, and do any slow
fulfillment work (sending emails, calling shipping APIs) asynchronously
after that ack rather than making the provider wait through it -- this
removes the timeout-triggered retry as a source of duplicates. Treat a
duplicate event ID as a successful no-op (return 200 immediately), not an
error, so the provider stops retrying it.

## Pitfalls
- Deduping on a hash of the payload instead of the provider's event ID --
  some providers include timestamps or evolving fields in the payload that
  make two deliveries of the "same" logical event hash differently.
- Doing the dedup check and the fulfillment side effect in separate
  database transactions -- a crash between the two leaves the event marked
  processed but fulfillment never happened, silently losing the order;
  they need to commit together (or fulfillment needs to be safely
  re-runnable from a durable queue keyed by the same event ID).
- Returning a non-2xx status for events your handler doesn't care about
  (unhandled event types) -- this trains the provider to keep retrying
  events you were correctly ignoring, and pollutes retry budgets that
  matter for the events you do care about; acknowledge and no-op instead.

## Verify
Replay the exact same webhook payload (same event ID) against the
endpoint two or three times in a row, either via the provider's dashboard
"resend" feature or a signed synthetic request, and confirm the
fulfillment side effect (order status, credit balance, email count) only
reflects one execution while every replay still receives a 2xx response.
