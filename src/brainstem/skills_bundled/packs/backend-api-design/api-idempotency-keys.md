---
name: api-idempotency-keys
description: Design or diagnose duplicate-side-effect bugs (double charges, duplicate orders) in POST/payment endpoints that get retried by clients or network layers.
triggers: ["double charge", "duplicate order created", "idempotency key", "retry causes duplicate", "double submit bug", "payment charged twice"]
permissions: ["READ"]
---

## Symptom
A user (or an automated retry from the client, a proxy, or a payment
provider's webhook) ends up triggering the same side effect twice --
double-charged payment, duplicate order row, duplicate email sent --
usually traced back to the same logical request being received and fully
processed more than once.

## Likely causes
1. **No idempotency mechanism at all** on an endpoint that performs a
   non-idempotent side effect (charge a card, create an order, send an
   email) -- any retry (client double-tap, network timeout causing the
   client to resend, load balancer retry) reprocesses it fully.
2. **A client-side double-submit** (double-clicked button, form
   resubmission on back-navigation) with no server-side protection,
   relying entirely on disabling the button client-side, which doesn't
   help for actual network retries.
3. **A webhook handler (e.g. from a payment provider) that isn't
   idempotent**, processing the same webhook event twice because
   providers explicitly document that webhooks can be delivered more
   than once and expect the receiver to dedupe.
4. **An idempotency key implemented but scoped too broadly or too
   narrowly** -- e.g. keyed only on user ID (so two genuinely different
   requests from the same user collide) or not persisted long enough
   (so a slow retry after the key expired reprocesses).

## Diagnose
- Check whether the endpoint accepts (and the client sends) an
  idempotency key header/field at all.
- For payment/webhook-specific duplicates, check the provider's event ID
  and whether it's been recorded and checked against before processing --
  most payment providers document this expectation explicitly.
- Reproduce by sending the exact same request twice in quick succession
  (same idempotency key if one exists) and confirming whether the side
  effect happens once or twice.

## Fix
- Require an idempotency key on any endpoint with a non-idempotent side
  effect: the client generates a unique key per logical operation (e.g. a
  UUID generated once when the user clicks "pay," reused on any retry of
  that same click), sent as a header or field.
- On the server, before processing, atomically check-and-record the key
  (e.g. an insert into a keys table with a unique constraint, or a
  conditional write) -- if the key was already seen, return the
  previously-computed result instead of reprocessing, rather than just
  rejecting the retry.
- For webhooks, record the provider's event ID in a dedup table with a
  unique constraint and check it before processing, treating a duplicate
  delivery as a no-op success (not an error) so the provider doesn't keep
  retrying.
- Scope idempotency keys to the specific operation and a reasonable time
  window (persisted long enough to cover realistic retry delays, e.g.
  24 hours), not indefinitely, and not scoped so broadly that unrelated
  requests collide.

## Pitfalls
- Disabling the submit button client-side is necessary UX but not
  sufficient protection -- it does nothing for network-level retries
  (timeouts causing the client library itself to resend) or for requests
  that bypass the UI entirely.
- Checking-then-inserting the idempotency key as two separate steps (not
  atomic) reintroduces a race condition under concurrent retries -- use a
  database unique constraint or an atomic compare-and-set, not a
  check-then-act pattern in application code.
- Returning a generic error for a duplicate key breaks legitimate retries
  that are supposed to be safe -- return the original successful result
  (or its status), not an error, when the key was already fully
  processed.

## Verify
Send the same request (same idempotency key/webhook event ID) multiple
times concurrently and confirm the side effect (charge, order row, email)
happens exactly once, and that every request received the same (correct)
response.
