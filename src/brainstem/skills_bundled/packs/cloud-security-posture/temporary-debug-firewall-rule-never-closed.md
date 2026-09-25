---
name: temporary-debug-firewall-rule-never-closed
description: A security group or firewall rule opened temporarily for debugging remains in place indefinitely, leaving an unnecessary open attack surface.
triggers: ["that port was only supposed to be open for a day", "who opened this to 0.0.0.0/0 and why is it still there", "temporary debug rule from months ago still active", "firewall rule with no expiration nobody remembers"]
permissions: ["READ"]
---

## Symptom

A security review or scan finds an inbound rule allowing broad access
(often `0.0.0.0/0` on a database, SSH, or RDP port) that, when traced
back, turns out to have been opened intentionally for a specific
debugging session weeks or months ago. The engineer who opened it either
forgot, changed teams, or assumed someone else would close it. No
expiration or follow-up ticket exists.

## Likely causes

- **The rule was opened directly via console/CLI during an active
  incident or debugging session** as the fastest way to unblock a
  connection test, with the mental model of "I'll close this when I'm
  done" but no actual mechanism enforcing that it happens.
- **The change was never tracked as a ticket or IaC change**, so there's
  no artifact anywhere (a ticket, a PR, a calendar reminder) that would
  later prompt anyone to ask "is this still needed?" -- it's invisible
  to any process except someone happening to notice it in a review.
- **The rule was scoped broadly ("just open it to any IP") instead of to
  the specific debugging source** (the engineer's actual IP, a VPN CIDR)
  because scoping precisely felt like extra friction during a
  time-pressured debugging session.
- **Ownership of the resource changed** (team reorg, project handoff)
  between when the rule was opened and now, so the people currently
  responsible for the resource have no context that the rule was ever
  meant to be temporary, and reasonably assume it's intentional
  since it's been there a long time.

## Diagnose

1. Enumerate all firewall/security-group rules with broad source ranges
   (`0.0.0.0/0`, `::/0`, or overly large CIDR blocks) across all
   accounts, specifically on sensitive ports (SSH/22, RDP/3389, database
   default ports, management interfaces).
2. For each, check the rule's creation timestamp against the cloud
   provider's audit log (CloudTrail, Cloud Audit Logs, Activity Log) to
   identify who created it and cross-reference against any ticket or PR
   from around that time explaining the intent.
3. Check actual connection logs (VPC Flow Logs, NSG flow logs, firewall
   logs) for real traffic hitting that rule's port from sources outside
   the expected/legitimate range, over a recent window, to establish
   whether it's still being used for anything or has simply been dormant
   attack surface.
4. Interview or message the identified creator/team if still reachable
   to confirm whether the original debugging need still exists in any
   form.

## Fix

Close or narrow every broad rule with no active legitimate traffic to
the minimum necessary source range, replacing `0.0.0.0/0` with specific
CIDRs, a bastion/VPN source, or removing the rule entirely if the
debugging need has passed. For any genuinely recurring debugging need,
replace the standing open rule with a just-in-time access mechanism
(a session-scoped security group rule created and auto-expired by
tooling, or a bastion host requiring per-session authorization) instead
of a permanently open rule. Going forward, require every manually
created firewall rule change to include an expiration tag or a linked
ticket, and add automated scanning that flags any broad-source rule
older than a defined threshold (e.g. 24-48 hours) for review.

## Pitfalls

Don't assume a rule is safe to leave just because current traffic logs
show no active abuse -- an unused broad-access rule is exactly the
"quiet until it's exploited" attack surface that gets found by an
external scanner or attacker performing reconnaissance, not by your own
traffic monitoring. Absence of observed abuse is not evidence of safety.

## Verify

Confirm the rule is removed or narrowed in the live environment and that
the corresponding infrastructure-as-code (if managed that way) reflects
the same change. Run the broad-source-rule scan again across all
accounts and confirm no rule exceeds the defined age threshold without
an attached expiration or justification, and confirm the debugging
workflow that originally needed the rule now uses the just-in-time
mechanism instead.
