---
name: overprivileged-role-granted-during-initial-setup-never-narrowed
description: A security audit finds a service identity holding broad admin-like permissions it was given once for convenience during initial setup and never reduced.
triggers: ["this role has way more access than it uses", "why does this service account have admin", "audit flagged overprivileged identity", "least privilege review found unused permissions"]
permissions: ["READ"]
---

## Symptom

A periodic access review, an external audit, or a cloud-native posture
tool flags a role, service account, or app registration whose granted
permissions vastly exceed what its actual API call history shows it
using. Nobody remembers deciding to grant that scope deliberately -- it
was applied once, early, and the team moved on. This is a cross-cloud
pattern independent of any one provider's policy syntax; it's about the
organizational habit that produces the gap, not the mechanics of any
single IAM engine.

## Likely causes

- **A wildcard or built-in "editor/contributor"-class role was attached
  during initial setup to unblock development**, with the intention to
  revisit and scope it down later -- a step that has no natural trigger
  to actually happen once things are working.
- **The identity's responsibilities shrank over time** (a service that
  used to write to five resource types now only reads from one, after a
  refactor), but permissions were additive-only and nobody removed the
  now-unused grants when the code changed.
- **Permissions were copied from a similar existing identity as a
  shortcut** ("just give it the same access as the other worker service")
  without verifying the new identity's actual needs matched the template
  it was copied from.
- **Nobody owns the recurring task of right-sizing permissions**, so
  even when usage data exists showing which permissions are actually
  exercised, no one is accountable for turning that data into a policy
  change.

## Diagnose

1. Pull the identity's actual permission usage from the provider's
   access-analysis tooling (e.g. AWS IAM Access Analyzer's "unused
   access" findings, GCP's Policy Analyzer / IAM Recommender, Azure AD's
   access reviews with sign-in and usage logs) over a window long enough
   to cover periodic jobs (90 days minimum, ideally a full year for
   anything with quarterly batch behavior).
2. Diff the granted policy against the observed-used permission set --
   list every granted action/role with zero corresponding usage events
   in that window.
3. Check the identity's creation date and its policy's last-modified
   date -- a large gap between "created" and "last permission change"
   with no corresponding code/architecture change is itself a signal the
   grant was never revisited.
4. Trace the identity's actual call sites in code (search for the
   SDK client or API calls it makes) to confirm what it structurally
   could ever need, independent of historical usage, since usage logs
   alone can miss rarely-exercised legitimate paths (annual reports, DR
   failover).

## Fix

Replace the broad grant with a policy scoped to the union of
(a) permissions with actual observed usage and (b) permissions the code
path structurally requires but exercises rarely -- verified by reading
the call sites, not just the usage log. Apply the change in a lower
environment first with the identity's normal workload running against
it, watching for permission-denied errors, before promoting to
production. Treat this as a recurring process, not a one-time cleanup:
schedule a periodic (quarterly) re-run of the same unused-access report
against every service identity, so scope creep is caught on a cadence
instead of only surfacing at audit time.

## Pitfalls

Don't narrow permissions based purely on a short usage window without
checking for infrequent-but-legitimate call paths -- cutting a
permission only exercised during month-end batch processing or annual
key rotation will pass testing all month and then break in production
on the one day it's needed. Always cross-reference usage data with a
code-level read of what the identity's execution paths can invoke.

## Verify

After narrowing, run the identity's full range of scheduled and
on-demand workloads (not just the common path) against the new policy in
a staging environment across at least one full cycle of its periodic
jobs, and confirm zero permission-denied errors before promoting to
production. Re-run the unused-access report 30 days after the change and
confirm the previously-flagged unused grants no longer appear.
