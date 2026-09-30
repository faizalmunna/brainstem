---
name: duplicate-charge-from-retried-payment-request
description: A customer's card is charged twice for one order after a network timeout or client double-submit caused the checkout request to be sent to the payment processor more than once.
triggers: ["customer charged twice", "duplicate charge on checkout", "payment retried and double billed", "double charge after timeout"]
permissions: ["READ"]
---

## Symptom
A customer reports (or support tickets show) two separate successful
charges for what should have been a single order -- typically both
charges are for the identical amount, seconds or minutes apart, and the
order/cart on the merchant side shows only one logical purchase attempt.
This is distinct from a webhook being processed twice (see
`duplicate-fulfillment-from-webhook-redelivery`) -- here the *charge
itself* was created twice at the processor, not just the notification
about one charge.

## Likely causes
1. **No idempotency key sent to the payment processor's charge/PaymentIntent
   API at all**, so when the client's HTTP request times out (the charge
   actually succeeded on the processor's side, but the response never made
   it back), the client's retry logic creates a brand-new charge instead of
   safely re-requesting the same one.
2. **Client-side double-submit** -- a double-tapped "Pay" button, a form
   resubmitted via back-button/refresh, or a mobile app that fires the
   request again on a slow spinner timeout -- with no server-side dedup,
   so two genuinely separate HTTP requests reach checkout and each creates
   its own charge.
3. **Idempotency key generated per HTTP attempt instead of per logical
   purchase intent** -- e.g. a new UUID is generated inside the retry loop
   rather than once when the user clicks "Pay," which defeats the purpose
   of the key because every retry looks like a new operation to the
   processor.
4. **Idempotency key reused across genuinely different orders** (e.g.
   keyed only on user ID + amount, so two different real purchases of the
   same price from the same user collide and the second is silently
   treated as a duplicate of the first, or vice versa the key space is too
   narrow and legitimate retries aren't recognized as retries).

## Diagnose
- Pull both charge records from the payment processor's dashboard/API and
  compare their idempotency key (or lack of one) -- most processors
  (Stripe, Adyen, Braintree) expose the key used on each charge object.
- Check the checkout service's logs for two separate outbound calls to the
  processor's charge endpoint for the same order ID/cart ID, and note the
  time gap -- a gap matching your HTTP client's timeout value strongly
  suggests a timeout-triggered retry, not a UI double-click.
- Check the client (browser network tab or mobile app logs) for two POSTs
  to your own `/checkout` endpoint -- if there are two, the bug is
  upstream of the payment call (double-submit); if there's only one but
  two calls left your server to the processor, the bug is in your
  server-side retry/timeout handling.
- Confirm whether your checkout endpoint or payment service passes an
  `Idempotency-Key` (or provider-equivalent) header at all -- absence of
  the header on either or both charge attempts is the most common root
  cause.

## Fix
Generate one idempotency key per logical purchase attempt -- created once
when the user initiates payment (e.g. when the "Pay" button is first
pressed, or when the order is created server-side) and persisted with the
order, not regenerated on each retry. Pass that same key on every attempt
to charge the processor for that order, including client-triggered retries
and your own server-side retry-on-timeout logic. Payment processors that
support idempotency keys (Stripe's `Idempotency-Key`, for example)
guarantee that a repeated request with the same key returns the original
result instead of creating a new charge, even if your first request's
response was lost to a network timeout. On your own server, also disable
the pay button immediately on click and reject a second `/checkout` POST
for an order that already has a charge in progress, so the double-submit
case is caught before it ever reaches the processor.

## Pitfalls
- Treating client-side button-disabling as sufficient protection -- it
  does nothing when the failure is a network timeout after the request
  already left the browser, which is the more common real-world cause of
  duplicate charges than double-clicks.
- Scoping the idempotency key too broadly (e.g. just the user ID) so that
  two legitimately different orders placed close together get merged into
  one charge, silently losing an order rather than preventing a duplicate.
- Generating a fresh key on every retry attempt "to be safe" -- this
  produces exactly the bug the key was meant to prevent, since the
  processor sees each retry as a new, distinct operation.

## Verify
Simulate a timeout by charging with a fixed idempotency key, killing the
connection before the response returns (or using the processor's test
mode to force a delayed response), then retrying with the same key and
order data -- confirm exactly one charge object exists at the processor
for that key, and that both the original and retried calls returned the
same charge ID.
