---
name: dunning-retries-against-already-fixed-payment-method
description: A failed-payment retry schedule keeps charging a customer's old expired or declined card even after they have already updated their payment method.
triggers: ["dunning still retrying old card", "customer updated card but still failing", "failed payment retry ignores new card", "subscription still charging expired card"]
permissions: ["READ"]
---

## Symptom
A subscription enters a dunning (failed-payment retry) sequence after a
decline, the customer updates their card in response to the failure
notification, but the next scheduled retry -- or several subsequent
retries -- still attempts the old card and fails again, sometimes leading
to an unnecessary suspension/cancellation email or actual downgrade even
though the customer took the corrective action they were asked to take.

## Likely causes
1. **The dunning schedule snapshots the payment method ID at the time the
   retry sequence starts** and always charges that specific ID on each
   scheduled attempt, never re-reading the customer's *current* default
   payment method at retry time.
2. **The card-update flow updates the customer's default payment method
   but doesn't touch (or notify) the already-in-flight dunning/retry job**,
   which was scheduled as a standalone task (e.g. a delayed job with the
   old card ID baked into its payload) independent of the customer record.
3. **The payment provider's own "smart retry" or subscription-recovery
   feature and the application's own custom dunning logic are both
   running simultaneously**, disagreeing about which payment method to
   use or double-scheduling retries, so a fix in one system doesn't
   propagate to the other.
4. **The new card is added but not set as default**, so the subscription
   is still explicitly attached to the old payment method ID even though
   a valid new card exists on the customer's account -- from the
   customer's point of view they "added their new card," but nothing
   repointed the subscription at it.

## Diagnose
- Pull the customer's payment-method history from the provider (list of
  cards added/removed and timestamps) and compare against the dunning
  job's scheduled execution log -- check specifically which payment
  method ID each retry attempt actually used, not just whether a retry
  happened.
- Check whether the subscription object's default/active payment method
  ID (in your database and at the provider) was updated when the customer
  added the new card, or whether it's still pointing at the old card ID.
- Check the dunning job's payload/parameters as stored at schedule time --
  if the payment method ID is embedded in the job data rather than looked
  up fresh at execution time, that's the smoking gun.
- Check for two independent retry mechanisms (e.g. provider-native smart
  retries plus an application-level cron/job) both acting on the same
  subscription, which can mask or duplicate the underlying bug.

## Fix
Make each dunning retry attempt look up the customer's *current* default
payment method at execution time, not the one captured when the retry
sequence was first scheduled -- the retry job should hold a reference to
the customer/subscription, not a frozen payment method ID. When a customer
successfully adds or updates a payment method, explicitly set it as the
subscription's active payment method immediately (not just "added to
their wallet") and, if a dunning sequence is currently in progress for
that subscription, trigger an immediate retry against the new method
rather than waiting for the next scheduled step -- this both recovers
revenue faster and avoids a confusing extra failure notification. If using
a provider's built-in smart-retry/recovery feature, don't run a parallel
custom dunning system against the same subscription; pick one source of
truth for retry scheduling and let card-update webhooks feed into that
single system.

## Pitfalls
- Canceling the dunning sequence entirely on any card update, without
  actually retrying -- this can leave the subscription in a failed state
  indefinitely if the customer added the card but the next natural retry
  is days away, silently delaying recovery even though the underlying
  cause looks fixed to the customer.
  the customer's new card immediately rather than assuming the update
  alone resolved things.
- Assuming "payment method updated" webhook events fire for every path a
  customer can use to add a card (e.g. a customer-portal self-service flow
  might not emit the same event as an API-driven update) -- verify all
  update entry points trigger the same reconciliation logic.
- Forgetting to also cancel/suppress the "your subscription will be
  canceled" warning emails once a successful retry happens out of the
  normal schedule -- customers get confused by a cancellation warning
  arriving after they already fixed the problem and were charged
  successfully.

## Verify
In a test environment, start a dunning sequence with a card that
deterministically declines, then before the next scheduled retry, update
the customer's payment method to a card that deterministically succeeds,
and confirm the next retry (whether triggered immediately or on schedule)
charges the new card ID, not the original one, and that the subscription
returns to active status without waiting out the full original dunning
schedule.
