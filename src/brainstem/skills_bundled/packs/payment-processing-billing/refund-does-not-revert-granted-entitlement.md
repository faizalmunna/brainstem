---
name: refund-does-not-revert-granted-entitlement
description: A payment is refunded through the processor but the subscription access, usage credits, or feature entitlement granted by that payment stays active on the account.
triggers: ["refunded customer still has access", "credits not removed after refund", "entitlement not revoked after refund", "refund didn't downgrade subscription"]
permissions: ["READ"]
---

## Symptom
A refund is issued (fully or partially) via the payment processor and
shows correctly on the processor's dashboard and on the customer's
statement, but the internal state that was granted because of the
original payment -- premium plan access, a pool of usage credits, an
unlocked feature, extended subscription period -- remains unchanged, so
the customer keeps the benefit they were refunded for, sometimes
indefinitely.

## Likely causes
1. **The refund flow only touches the payment processor**, e.g. a support
   agent clicks "refund" directly in the processor's dashboard, which
   never calls back into the application at all, so there is no code path
   that ever runs to revoke anything -- the two systems are only loosely
   connected through documentation/process, not code.
2. **A refund webhook event exists and is received, but the handler only
   logs/records the refund for accounting purposes** and was never wired
   to the entitlement-revocation logic, because refunds were treated as a
   finance concern rather than an entitlements concern when originally
   built.
3. **Partial refunds are not distinguished from full refunds**, and the
   revocation logic (if it exists at all) only handles the full-refund
   case, silently no-op'ing on partial refunds -- which are common (e.g.
   refunding one seat out of a multi-seat plan, or a prorated partial
   refund on cancellation).
4. **Entitlement was granted by a separate system from the one that
   processes payment status** (e.g. a licensing service or usage-credit
   ledger that was updated once at purchase time and has no ongoing
   relationship to the payment's later lifecycle), so there's no natural
   place for a refund event to land.
5. **Race between refund processing and usage** -- credits or entitlement
   granted by the payment were already partially consumed (API calls made,
   features used) before the refund posts, and the revocation logic
   doesn't account for already-consumed usage, either over- or under-
   clawing back.

## Diagnose
- Trace a specific refunded transaction: confirm the refund exists at the
  processor, then check whether *any* webhook event for that refund was
  received and logged by the application, and if so, what the handler did
  with it (or didn't).
- Grep the webhook handler code for the refund event type (e.g.
  `charge.refunded`, `refund.updated`) and confirm whether it exists as a
  handled case at all, versus falling through to a default/ignored branch.
- Check whether the entitlement/credit-granting code and the payment-
  webhook-handling code are even in the same service -- if entitlements
  live in a different system, check what integration (if any) connects
  them for the refund direction specifically (the grant direction, at
  purchase, is usually well-tested; the revoke direction on refund often
  isn't).
- For a partial refund specifically, check whether the revocation logic
  has any partial-amount handling or only a binary "was this order ever
  refunded" check.

## Fix
Treat refund events from the payment provider as first-class inputs to
the entitlement system, not just an accounting record: handle the
provider's refund webhook (and reconcile against the provider's refund
list, per the reconciliation pattern used for other missed-event cases)
by computing what portion of the original entitlement corresponds to the
refunded amount and reversing exactly that portion -- full refund revokes
the full grant, a partial refund revokes a proportional amount (e.g. a
50% refund on a credit pack claws back 50% of the credits, floored at
zero already-consumed credits, never going negative). Route refunds that
originate in a support/finance tool through the same application API path
that a customer-initiated refund would use, rather than allowing direct
processor-dashboard refunds to bypass application logic entirely --
if the processor's dashboard must remain usable for support staff, add a
reconciliation job that catches refunds initiated there and applies the
same revocation logic after the fact.

## Pitfalls
- Revoking the full entitlement on any refund regardless of amount --
  this over-penalizes customers who received a small goodwill partial
  refund and creates support escalations of its own.
- Clawing back usage credits below zero when the customer already
  consumed more than the refunded portion -- decide explicitly (and
  document) whether this creates a negative balance that blocks future
  usage, or is capped at zero with the difference absorbed, rather than
  leaving it as whatever the arithmetic happens to produce.
- Only wiring up revocation for the "customer requests a refund" support
  flow while missing chargebacks/disputes, which arrive as a different
  webhook event type but have the same entitlement implication and are
  easy to forget as a separate case.

## Verify
Issue a full refund on a test transaction that granted a specific,
countable entitlement (e.g. 100 usage credits or a plan upgrade) and
confirm the entitlement is fully reverted; separately issue a partial
refund (e.g. 50%) on another test transaction and confirm the entitlement
is proportionally reduced, not left untouched and not fully revoked.
