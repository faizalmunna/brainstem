---
name: involuntary-churn-not-distinguished-from-voluntary-cancellation
description: A subscription is canceled and reported as customer churn when the real cause was exhausted payment retries, making retention metrics and win-back campaigns target the wrong customers.
triggers: ["churn numbers look wrong", "canceled customers who never asked to cancel", "dunning cancellation counted as voluntary churn", "win-back campaign targeting failed payments"]
permissions: ["READ"]
---

## Symptom
Subscription-cancellation analytics, churn dashboards, or win-back email
campaigns treat all "subscription ended" events identically, but a
significant fraction of them are actually the terminal step of a failed-
payment/dunning sequence (the customer never clicked "cancel" and may not
even know their access lapsed) rather than a deliberate decision to leave
-- and downstream systems (churn-rate reporting, "sorry to see you go"
surveys, exit-discount offers) respond as if every case were the latter,
producing nonsensical customer communication and misleading retention
metrics.

## Likely causes
1. **The subscription-cancellation event/webhook fired at the end of a
   dunning sequence uses the same event type/status as an explicit
   customer-initiated cancellation**, so any downstream consumer that
   only checks "is this subscription canceled" can't tell the two apart
   without also checking the cancellation reason field (if one even
   exists).
2. **No cancellation-reason field is captured or propagated at all** --
   the subscription record just flips to `canceled` regardless of whether
   the trigger was a customer clicking cancel, an admin action, or dunning
   exhaustion, so the distinction is lost at the point of state change and
   can't be recovered later without cross-referencing separate payment-
   attempt logs.
3. **Analytics/reporting queries group by subscription end date and status
   only**, built before involuntary churn was a distinct concern, and
   nobody revisited the query when the dunning system was added later --
   a schema/process drift rather than a one-time design mistake.
4. **Win-back and retention tooling is wired to any "canceled" event
   generically**, on the reasonable-sounding assumption that all canceled
   customers are the same audience, without a separate segment for
   payment-recoverable churn (who need a "update your card" message) vs.
   product/value churn (who need a different message entirely).

## Diagnose
- Pick a sample of recently canceled subscriptions and check each one's
  event history: did a `subscription.canceled`-type event follow a series
  of failed-charge events for that subscription (involuntary), or was
  there a direct customer action (a DELETE/cancel API call, a portal
  click, a support ticket) with no preceding payment failures (voluntary)?
- Check whether the subscription/cancellation database schema has any
  reason/source field at all, and if it exists, check what fraction of
  recent cancellations have it populated vs. null -- a high null rate
  indicates the field exists but isn't consistently set at every
  cancellation code path.
- Check the win-back or churn-survey trigger logic for what condition it
  fires on -- if it's simply "subscription status changed to canceled,"
  that confirms it isn't reason-aware.
- Cross-reference total canceled count against dunning-exhausted count for
  the same period from the payment-retry system's own logs -- the overlap
  size quantifies how much of "churn" is actually involuntary in this
  specific system.

## Fix
Add an explicit, always-populated cancellation-reason/source field on the
subscription-cancellation event and record (e.g.
`customer_requested` / `admin_action` / `payment_failure_exhausted` /
`fraud_hold`, etc.), set at every code path that can end a subscription,
not just the primary customer-facing one. Update churn reporting to
segment by this field rather than treating all cancellations as one
population, since voluntary and involuntary churn have different causes,
different remediation (win-back messaging vs. payment-recovery messaging),
and arguably belong in different metrics for judging product health versus
payment-infrastructure health. Route involuntary-churn subscriptions to a
distinct, payment-focused recovery flow (e.g. "we couldn't renew your
card, here's a link to update it and reactivate with your data intact")
instead of a generic voluntary-churn win-back campaign that talks about
missing features or asks a satisfaction survey question that makes no
sense to someone who didn't choose to leave.

## Pitfalls
- Adding the reason field only to the newest cancellation code path and
  leaving older paths (e.g. an admin bulk-cancellation script, a fraud-
  hold cancellation job) still writing null/unset reasons, so the
  historical fix looks complete in new data but old reporting gaps
  persist.
- Conflating "involuntary churn" with "definitely recoverable" -- some
  dunning-exhausted cancellations really are customers who no longer want
  the product and simply didn't bother explicitly canceling; the reason
  field changes what message to send, not a guarantee that a win-back
  attempt will succeed.
- Backfilling historical cancellation reasons by inference (e.g. "had a
  failed charge in the prior 30 days therefore involuntary") without
  flagging inferred records as such -- silently mixing inferred and
  directly-recorded reasons undermines trust in the metric going forward.

## Verify
Trigger a subscription cancellation through the dunning-exhaustion path
and, separately, through the explicit customer-cancel API/portal action in
a test environment, and confirm the resulting subscription records have
distinct, correctly-populated reason values -- then confirm the churn
reporting query, when run against both test records, correctly buckets
them into separate segments rather than a single combined "canceled"
count.
