---
name: vendor-contractor-access-not-revoked-after-engagement
description: A third-party vendor or contractor retains cloud access broader than their engagement scope and it isn't revoked when the engagement ends.
triggers: ["contractor still has access months after their contract ended", "vendor account was never offboarded", "third party access wider than what they needed", "audit found an external account still active"]
permissions: ["READ"]
---

## Symptom

An access review or audit turns up an active account belonging to a
contractor, agency, or vendor whose engagement ended weeks or months
earlier -- the account was never disabled, and in many cases its
granted permissions were broader than the original engagement's actual
scope even while the engagement was active.

## Likely causes

- **Vendor/contractor accounts are provisioned outside the standard
  employee onboarding/offboarding system** (created directly by a
  project lead who needed to unblock the vendor quickly), so they're
  invisible to whatever automated offboarding process exists for regular
  employees tied to an HR system's termination event.
- **No engagement end date was ever recorded against the account at
  provisioning time**, so there's no scheduled trigger to prompt a
  review or automatic expiration -- the account simply persists until
  someone happens to notice it during an unrelated audit.
- **Access was granted by copying an internal employee's role/group
  membership as a shortcut** ("just give them the same access as the
  team") rather than scoping to the specific systems and actions the
  engagement actually required, so even during active engagement the
  access exceeded the real need.
- **Offboarding responsibility is unclear between the vendor management
  function (who owns the contract) and IT/security (who owns account
  deprovisioning)**, so each assumes the other will act when the
  engagement ends, and neither does.

## Diagnose

1. Cross-reference the list of all active accounts tagged or
   identifiable as external/vendor/contractor against the current
   vendor/contract management system's list of active engagements --
   any account with no corresponding active contract is a stale
   candidate for immediate review.
2. For accounts confirmed still tied to an active engagement, compare
   the account's actual granted permissions against the engagement's
   documented scope of work to identify any excess beyond what the
   engagement requires.
3. Check the account provisioning record (ticket, PR, or audit log
   entry for account creation) for whether an expiration date or
   scheduled review was ever set at creation time -- absence indicates
   a structural gap, not just a one-off miss.
4. Check sign-in/activity logs for each flagged account to determine
   whether it's still actively being used, which affects urgency and
   also indicates whether credentials may have been shared or reused
   beyond the original individual.

## Fix

Require every vendor/contractor account to be provisioned with a
mandatory expiration date tied to the contract end date at creation
time (many identity providers support scheduled account expiration
natively), so deprovisioning happens automatically rather than depending
on someone remembering. Scope access at provisioning to the specific
systems and least-privilege actions the statement of work describes,
using a dedicated external-identity group/role template distinct from
internal employee roles, rather than copying an employee's access as a
shortcut. Establish an explicit, single owner (typically IT/security,
triggered by a vendor-management system event) for the deprovisioning
step, with a recurring reconciliation report comparing active external
accounts against active contracts on a regular cadence as a backstop for
when the automated expiration path is bypassed.

## Pitfalls

Don't rely solely on the vendor or contracting manager to remember to
request offboarding -- the person most motivated to keep access working
smoothly during the engagement has no corresponding incentive to
proactively request its removal afterward, so the deprovisioning trigger
needs to come from a system event (contract end date), not a
remembered human action.

## Verify

Confirm the cross-reference between active external accounts and active
contracts shows zero orphaned accounts. For a newly provisioned vendor
account, confirm it was created with an expiration date set and that
attempting to authenticate with it after that date fails automatically
without manual intervention.
