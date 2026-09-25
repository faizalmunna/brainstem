---
name: iam-service-account-impersonation-permission-denied
description: A workload correctly configured to impersonate a GCP service account still gets a permission-denied error because a required IAM binding exists at the wrong resource level.
triggers: ["gcp service account impersonation denied", "iam permission denied despite correct role", "service account token creator missing", "gcp cross project permission denied"]
permissions: ["READ"]
---

## Symptom

An application or CI pipeline configured to impersonate a GCP service
account (rather than using a downloaded key file) fails with a
permission-denied error when attempting to act as that service account,
even though the target service account appears to have all the roles
it needs for the actual operation being attempted.

## Likely causes

- **The calling identity (a user, another service account, a workload
  identity binding) lacks the `roles/iam.serviceAccountTokenCreator` (or
  `serviceAccountUser`, depending on the exact impersonation mechanism)
  role on the *target* service account specifically** -- this is a
  separate permission from whatever roles the target service account
  itself has on other resources, and is the single most common cause of
  this exact symptom.
- **The IAM binding exists but at the wrong resource level** -- granted
  at the project level when the specific resource (the service account
  itself) requires its own binding, or vice versa, depending on how the
  organization's IAM policy is structured.
- **Workload Identity Federation (for external workloads impersonating a
  GCP service account) is misconfigured** -- the attribute mapping or
  condition on the workload identity pool provider doesn't match what the
  external token actually presents, so the impersonation request is
  rejected before even reaching the target service account's own
  permissions.
- **An organization policy constraint blocks service account key
  creation or cross-project impersonation** entirely, independent of any
  IAM role grants, which produces a similar-looking denial for an
  unrelated, policy-level reason.

## Diagnose

1. Read the exact error message closely -- GCP's IAM error messages
   typically distinguish between "missing permission on the calling
   identity" versus "missing permission on the target resource," which
   narrows down which side of the impersonation relationship is
   misconfigured.
2. Check the target service account's IAM policy (not the roles it
   holds on other resources, but who is allowed to *act as* it) for
   whether the calling identity has the token-creator/service-account-
   user role specifically on that service account.
3. For Workload Identity Federation, verify the attribute mapping/
   condition configuration against the actual claims present in the
   external identity token being presented.
4. Check applicable organization policies for constraints on service
   account key creation, cross-project access, or domain-restricted
   sharing that might independently block the operation.

## Fix

Grant the calling identity the appropriate impersonation role (commonly
`roles/iam.serviceAccountTokenCreator`) directly on the specific target
service account resource, rather than assuming a broader project-level
role grant covers it. For Workload Identity Federation setups, align the
attribute mapping/condition precisely with the actual external token
claims, testing with a minimal reproduction rather than debugging inside
a complex CI pipeline. Where an organization policy is blocking the
operation intentionally (for security reasons), work within that policy
(e.g. using Workload Identity Federation instead of key files, if that's
what the policy is steering toward) rather than requesting a blanket
policy exception.

## Pitfalls

Don't grant overly broad IAM roles (e.g. `roles/owner`, or
`serviceAccountTokenCreator` at the organization level) just to resolve
the immediate error faster -- scope the impersonation permission to the
specific service account(s) actually needed, following least-privilege
practice, since this is exactly the kind of permission that if broadly
granted, allows acting as many identities across the organization.

## Verify

After correcting the IAM binding (or Workload Identity Federation
configuration), retry the exact original impersonation operation and
confirm it succeeds. Confirm the calling identity still cannot
impersonate *other* service accounts it wasn't intentionally granted
access to, verifying the fix was properly scoped rather than
accidentally broadened.
