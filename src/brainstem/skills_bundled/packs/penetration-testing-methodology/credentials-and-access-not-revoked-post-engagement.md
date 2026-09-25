---
name: credentials-and-access-not-revoked-post-engagement
description: Test accounts, VPN access, or elevated credentials created for a penetration testing engagement remain active long after the engagement ends, becoming an unmonitored access path.
triggers: ["pentest accounts never deactivated", "test credentials still active after engagement", "vpn access left open after security test", "unrevoked access from prior engagement"]
permissions: ["READ"]
---

## Symptom

Long after a penetration testing engagement has concluded and the report
delivered, an audit or a security review discovers that credentials,
accounts, or network access (VPN, API keys, elevated permissions)
created specifically for that engagement are still active -- an
unmonitored, unnecessary access path that's existed for months or longer
with no one actively responsible for it.

## Likely causes

- **No formal offboarding step was included in the engagement process**
  -- provisioning test access was handled explicitly at the start, but
  deprovisioning it at the end was left implicit, assumed to happen
  "naturally" without anyone being specifically accountable for it.
- **Access was provisioned through an ad hoc, undocumented process**
  (a quick manual account creation to unblock the engagement rather
  than through the organization's standard access-request workflow),
  so it doesn't show up in whatever access-review process normally
  catches provisioned-but-unused accounts.
- **The engagement's point of contact (who would have known to revoke
  access) left the organization or changed roles** before follow-up
  happened, and the knowledge of what access existed and needed revoking
  left with them.
- **No periodic access review/audit process exists at all** that would
  independently catch a forgotten account regardless of how it was
  originally provisioned, relying entirely on someone remembering to
  clean up.

## Diagnose

1. Inventory all credentials/accounts/access grants created for the
   specific engagement (checking provisioning records, ticket history,
   or directly asking the vendor/tester what was provided) and confirm
   which are still active.
2. Check whether a formal offboarding step exists in the engagement
   process template at all, or whether it's implicit/undocumented.
3. Check activity logs on the still-active credentials to determine
   whether they've actually been used since the engagement ended
   (confirming whether this is a dormant risk or an active concern).
4. Review how the access was originally provisioned to understand
   whether it went through a process that should have included automatic
   expiration.

## Fix

Add an explicit, required offboarding checklist item to the engagement
process -- revoking all test accounts, VPN access, and credentials as a
mandatory step before the engagement is considered fully closed, with a
specific named owner responsible for confirming it's done. Where
possible, provision engagement-specific access with an automatic
expiration date set at provisioning time (many identity/access systems
support time-limited grants), so access is revoked by default even if
the manual offboarding step is missed. Establish a periodic (quarterly or
similar) access review that would independently catch any forgotten
account regardless of how it was provisioned, as a backstop.

## Pitfalls

Don't revoke access immediately upon report delivery without confirming
the retest phase (if scheduled) doesn't still need it -- coordinate
offboarding timing with the full engagement lifecycle including any
planned remediation verification, rather than revoking prematurely and
having to re-provision.

## Verify

Confirm all identified engagement-specific access has been fully
revoked, and confirm this via an independent check (not just the
revoking team's own confirmation) -- attempt to authenticate with the
old credentials and confirm access is genuinely denied. Add the
offboarding checklist item to the standard engagement template and
confirm it's followed for the next engagement.
