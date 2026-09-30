---
name: subscription-renewal-fails-on-expired-card-with-no-warning
description: A recurring subscription renewal fails unexpectedly because the customer's card expired, and the customer receives no advance warning before the failed charge and service interruption.
triggers: ["subscription renewal failed expired card", "no warning before card expired", "churned customer says card just expired", "involuntary churn expired card"]
permissions: ["READ"]
---

## Symptom
A subscription that had been renewing successfully for months suddenly
fails to renew, the customer is surprised (they didn't realize their card
had expired), and support logs show no proactive notification was sent
before the failed charge -- the first the customer hears of it is a
failure/dunning email or a service suspension notice, even though the
card's expiration date was known and stored well in advance.

## Likely causes
1. **No proactive expiration check exists at all** -- the system only
   discovers a card is expired reactively, at the moment it attempts to
   charge it, rather than scanning stored payment methods ahead of each
   renewal date for cards expiring soon.
2. **The payment processor's card-updater service (e.g. account updater/
   Visa Account Updater equivalents that many processors integrate) isn't
   enabled or isn't being listened to** -- many processors can
   automatically refresh expired-but-reissued card numbers/expiry dates
   behind the scenes via network updater programs, and this either isn't
   turned on or the webhook telling the application about the update is
   ignored.
3. **Expiration data is stored at the time the card was added and never
   refreshed**, so even if the customer's bank reissued a new card with a
   new expiry (common with card networks' auto-update programs), the
   application's stale local copy still thinks the old expiry is current
   or, conversely, doesn't know a network-side update already fixed it.
4. **Notification logic checks expiration against the wrong reference
   date** -- e.g. comparing against "today" only on the exact renewal day
   instead of scanning some window ahead (a week or a month out), so there
   is no time between the warning and the actual failed charge for the
   customer to act.

## Diagnose
- Query stored payment methods for the affected customer and confirm the
  stored expiration date versus what the processor currently reports for
  that card (if the processor's account-updater feature is enabled, it
  may already have newer data than what's cached locally).
- Check whether any scheduled job exists that scans upcoming renewals
  (e.g. next 7-30 days) against stored card expiration dates -- if no such
  job exists, that's the primary gap.
- Check the processor's dashboard/settings for whether an account-updater
  or card-updater feature is enabled for the account, and if enabled,
  whether the webhook event for a card update is handled anywhere in the
  codebase (grep for the event name, e.g. Stripe's
  `payment_method.automatically_updated` or the provider equivalent).
- Check the notification system's logs for whether an expiration-warning
  email was ever queued for this customer before the failed charge --
  absence confirms the proactive path never ran, not just that the
  customer ignored it.

## Fix
Add a scheduled job that runs ahead of each billing cycle (e.g. daily,
scanning renewals due in the next 7-30 days) and flags any payment method
expiring before its next scheduled charge, triggering a proactive
"update your card" notification with enough lead time for the customer to
act before the actual renewal attempt -- this converts a reactive failure
into a preventable one. Enable and integrate the payment processor's
card/account-updater feature if available, and handle its update-
notification webhook by refreshing the stored expiration (and card
number token, if changed) so silently-reissued cards continue working
without any customer action or false expiration warnings. Combine both:
account-updater handles the "bank issued a new card with the same
program, transparently" case, and the proactive-scan-plus-notification
handles the "customer needs to actually go add a different card" case,
since not all expirations are auto-resolved by the network.

## Pitfalls
- Relying solely on the account-updater feature and skipping proactive
  customer notification entirely -- account-updater programs don't cover
  every card, issuer, or expiration scenario (e.g. a card that expired
  because the account was closed, not just reissued), so some fraction of
  customers still need an explicit heads-up.
- Sending the expiration warning so close to the renewal date that there's
  no practical time to act (e.g. same-day) -- defeats the purpose of being
  proactive; use a lead time long enough for a customer to actually update
  a card (a week is a reasonable minimum).
- Sending repeated warning emails every day for weeks once a card is
  flagged as expiring, without suppressing them once the customer actually
  updates their payment method -- causes notification fatigue and support
  complaints independent of the original problem.

## Verify
Seed a test customer's payment method with an expiration date inside the
proactive-scan window (e.g. expiring in 10 days when the scan window is
30 days), run the scheduled scan job manually, and confirm exactly one
warning notification is generated for that customer; then update the
test payment method to a non-expiring card and re-run the scan, confirming
no further warnings are sent for that subscription.
