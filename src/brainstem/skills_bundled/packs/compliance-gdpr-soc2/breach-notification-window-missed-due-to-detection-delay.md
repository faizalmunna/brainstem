---
name: breach-notification-window-missed-due-to-detection-delay
description: A data breach isn't reported within the legally required notification window because the organization took too long to detect and confirm the breach had occurred in the first place.
triggers: ["breach notification deadline missed", "72 hour gdpr notification missed", "took too long to detect breach", "data breach reported late"]
permissions: ["READ"]
---

## Symptom

A data breach (GDPR requires notification to the relevant authority
within 72 hours of becoming aware of a breach, and other frameworks have
their own windows) is reported after the required notification deadline
has already passed -- not because the organization delayed reporting a
known breach, but because the breach wasn't detected and confirmed
until after enough time had elapsed that the deadline, measured from
actual occurrence, was already missed.

## Likely causes

- **No monitoring/alerting exists that would detect the specific type of
  unauthorized access or data exposure that occurred**, so the breach
  persisted silently until discovered through an unrelated event (a
  customer report, a security researcher, a routine audit) long after it
  began.
- **Logs that would have shown the breach activity weren't retained long
  enough** to reconstruct exactly when the breach began, once it was
  eventually discovered, making even the "when did we become aware"
  timeline harder to establish precisely and defend.
- **An internal team noticed suspicious activity but didn't recognize its
  significance or escalate it promptly** to whoever is responsible for
  breach determination and regulatory notification, so time was lost
  between initial suspicion and formal recognition.
- **No clear internal process exists for how a suspected breach moves
  from initial detection to legal/compliance confirmation and
  notification**, so even once something was noticed, ambiguity about
  ownership and process consumed time that ate into the notification
  window.

## Diagnose

1. Reconstruct the actual timeline: when the breach began, when it was
   first noticed by anyone internally, when it was formally confirmed as
   a reportable breach, and when notification was actually sent.
2. Identify which specific stage(s) consumed the most time relative to
   what should have been possible -- detection delay, escalation delay,
   or confirmation/notification-process delay.
3. Check what monitoring/alerting existed for the specific type of
   unauthorized activity involved, and whether it should have caught the
   breach earlier than it actually did.
4. Check log retention for the relevant systems and whether it was
   sufficient to fully reconstruct the breach timeline once
   investigation began.

## Fix

Improve detection capability (monitoring/alerting) for the specific
category of unauthorized access that caused this breach, so a similar
future incident is caught closer to when it begins rather than much
later. Establish and train the team on a clear internal escalation path
from "someone notices something suspicious" to "compliance/legal makes
a formal breach determination," so time isn't lost to ambiguity about
who owns that decision. Extend log retention where it was insufficient
to support timely breach investigation. Build a practiced incident
response process specifically for breach scenarios, including a
pre-drafted notification template and clear ownership, so the
confirmation-to-notification stage itself is fast once a breach is
confirmed.

## Pitfalls

Don't treat "we detected and reported within 72 hours of *discovering*
it" as automatically fully compliant without examining whether detection
itself was unreasonably delayed by a fixable monitoring gap -- regulators
and courts have scrutinized organizations for how quickly they *should*
have become aware, not just measured strictly from actual awareness;
closing detection gaps is a genuine part of compliance, not just a nice-
to-have.

## Verify

Confirm the specific monitoring/alerting gap identified is now closed by
testing it against a simulated version of the same activity pattern in a
non-production environment. Run a tabletop exercise simulating a new
suspected breach and confirm the escalation and notification process
now completes within an appropriate fraction of the required window,
leaving buffer for genuine investigation time.
