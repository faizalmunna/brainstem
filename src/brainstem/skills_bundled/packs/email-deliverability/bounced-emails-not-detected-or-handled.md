---
name: bounced-emails-not-detected-or-handled
description: An application keeps sending emails to addresses that consistently bounce, with no process detecting or suppressing them, gradually damaging sender reputation.
triggers: ["bounced emails not handled", "sending to invalid addresses repeatedly", "bounce rate hurting deliverability", "no suppression list for bounces"]
permissions: ["READ"]
---

## Symptom

Overall email deliverability degrades gradually over time, and
investigation reveals the application keeps sending to a growing set of
email addresses that consistently bounce (invalid addresses, full
mailboxes, addresses that no longer exist) -- with no automated process
detecting these bounces and suppressing future sends to those addresses,
allowing the bounce rate to accumulate and damage overall sender
reputation.

## Likely causes

- **No bounce webhook/notification handling was implemented** from the
  email sending provider, so bounce events are technically available
  from the provider but never actually consumed or acted upon by the
  application.
- **Bounces are received and logged but never actually suppress future
  sends** to the same address -- the application has visibility into
  which addresses bounced but no enforcement mechanism preventing
  repeated attempts.
- **Hard bounces (permanent failures, like a non-existent address) and
  soft bounces (temporary failures, like a full mailbox) are treated
  identically**, either suppressing too aggressively on a transient
  issue or not suppressing at all on a permanent one.
- **Email addresses are collected once at signup with no ongoing
  validation**, so addresses that were valid at signup but have since
  become invalid (an abandoned account, a company domain shut down)
  accumulate over time with no process to detect and handle this decay.

## Diagnose

1. Check whether the email sending provider's bounce webhook/notification
   feature is configured and whether the application actually has an
   endpoint consuming it.
2. If bounces are received, check whether any suppression logic exists
   that prevents future sends to a bounced address, or whether bounce
   data is only logged without enforcement.
3. Review current bounce rate and compare against the sending provider's
   documented healthy-range guidance to quantify the actual severity.
4. Check whether hard and soft bounces are distinguished, and whether
   each is handled with an appropriately different suppression policy.

## Fix

Implement bounce webhook handling that updates a suppression list --
immediately and permanently suppressing addresses with hard bounces,
and applying a more lenient policy (a few retries with backoff, or
suppression after repeated soft bounces) for soft bounces. Check this
suppression list before every send, preventing any future attempt to a
known-bad address regardless of what triggered the original send
request. Periodically validate stored email addresses (via a validation
service, or by observing engagement/bounce patterns over time) to catch
decay in previously-valid addresses proactively rather than only
reactively after a bounce occurs.

## Pitfalls

Don't suppress an address permanently after a single soft bounce (a
temporarily full mailbox, a transient server issue) -- that can
permanently lose a legitimate, still-valid recipient over a one-time
transient condition; reserve permanent suppression for hard bounces or a
documented pattern of repeated soft bounces.

## Verify

Confirm bounce webhook events are actually being received and processed
by checking recent bounce events against the suppression list state.
Attempt to send to a known-suppressed address and confirm the
application correctly blocks the send rather than attempting it.
Monitor overall bounce rate over subsequent weeks and confirm it trends
down toward a healthy range.
