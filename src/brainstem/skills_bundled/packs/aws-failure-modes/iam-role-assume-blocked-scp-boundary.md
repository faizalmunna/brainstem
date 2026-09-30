---
name: iam-role-assume-blocked-scp-boundary
description: An IAM role cannot be assumed even though its trust policy correctly lists the calling principal, because an organization SCP or permissions boundary blocks it separately.
triggers: ["assumerole access denied trust policy looks fine", "sts assumerole fails despite correct trust relationship", "scp blocking role assumption", "permissions boundary denying sts assumerole", "cannot assume role organizations policy"]
permissions: ["READ"]
---

## Symptom
`sts:AssumeRole` fails with `AccessDenied` for a principal that is
explicitly and correctly listed in the target role's trust policy
(`Principal`/`Condition` block reviewed line by line and matches), and
the trust policy alone would normally be sufficient -- the failure
persists even after re-verifying and re-saving the trust policy multiple
times.

## Likely causes
1. **A Service Control Policy (SCP) at the AWS Organizations level denies
   `sts:AssumeRole`** for this account, OU, or specific role ARN pattern
   -- SCPs apply account-wide regardless of any IAM policy or trust
   policy inside the account, and are frequently owned by a different
   team, invisible from within the member account's own IAM console view
   in the same place trust policies are edited.
2. **A permissions boundary attached to the calling principal (the IAM
   user/role trying to assume) doesn't include `sts:AssumeRole`** in its
   allowed actions -- a permissions boundary caps the *maximum* effective
   permissions of the identity it's attached to, independent of what its
   identity policies grant, so even a caller with an explicit `Allow
   sts:AssumeRole` in its own policy is still blocked if the boundary
   doesn't also allow it.
3. **A permissions boundary on the *target* role itself** restricts what
   the role can be used for, separate from who can assume it -- this is
   a different, less commonly checked boundary than the caller-side one
   in cause 2.
4. **The trust policy's `Condition` block (e.g., `sts:ExternalId`,
   `aws:PrincipalOrgID`, MFA condition) is satisfied in the console test
   but not in the actual calling context** -- e.g., MFA is required by
   the trust policy but the caller's session wasn't established with
   MFA, or an `ExternalId` is required and the caller's `AssumeRole` call
   doesn't pass one.
5. **Session tags or a tag-based condition in either the trust policy or
   an SCP** restrict assumption based on `aws:PrincipalTag` or session
   tags that aren't being set by the calling identity's own policy,
   causing a deny that has nothing to do with the trust relationship
   itself.

## Diagnose
- Use `aws iam simulate-principal-policy` for the calling identity with
  action `sts:AssumeRole` and the target role's resource ARN -- this
  evaluates identity policies and permissions boundaries together and
  will surface a boundary-caused deny explicitly.
- Check CloudTrail for the actual `AssumeRole` API call's error: look for
  `explicit deny in a service control policy` vs. `explicit deny in a
  permission boundary` vs. `explicit deny in an identity-based policy` in
  the event detail -- AWS's own error messages usually name which
  mechanism produced the deny, and this is the fastest way to stop
  guessing.
- If in an AWS Organizations-managed account, check with whoever manages
  the Organization (or `aws organizations list-policies-for-target
  --target-id <account-id> --filter SERVICE_CONTROL_POLICY`) for any SCP
  affecting this account/OU, and read it specifically for `sts:AssumeRole`
  or a wildcard `Deny` with a `NotAction` exclusion.
- Check both the calling principal and the target role for an attached
  permissions boundary (`GetUser`/`GetRole` show
  `PermissionsBoundary.PermissionsBoundaryArn`) -- check both directions,
  since either can independently block the assumption.
- Re-examine the trust policy's `Condition` block for MFA or ExternalId
  requirements, and confirm the actual `AssumeRole` call (SDK/CLI
  invocation) includes matching parameters (`--external-id`,
  MFA-authenticated session).

## Fix
Identify which specific layer is producing the deny via CloudTrail/policy
simulator before changing anything, since the trust policy is very likely
already correct and further edits to it will not help. If an SCP is the
cause, work with the Organization's management account owner to add an
exception (e.g., scope the SCP's deny with a `Condition` excluding the
specific role/account, or move the account to an OU with a less
restrictive SCP) rather than trying to work around it from inside the
member account, which is not possible by design. If a permissions
boundary is the cause, add the specific action (`sts:AssumeRole`, scoped
to the specific target role ARN if possible rather than `*`) to the
boundary policy, understanding that a boundary is meant to be a
deliberate ceiling -- widen it narrowly, not by removing it. For
condition mismatches, correct the calling code/session to actually
satisfy the condition (pass the external ID, authenticate with MFA)
rather than removing the condition from the trust policy, since it likely
exists for a real security reason (e.g., confused-deputy prevention).

## Pitfalls
Removing or drastically widening an SCP or permissions boundary to "make
it work" defeats the governance purpose those mechanisms exist for --
SCPs and boundaries are usually put in place deliberately by a security
or platform team, and bypassing them (or asking for `*` access) to
resolve one blocked workflow can reopen a previously-closed risk across
the entire account/OU. Also, repeatedly re-saving the trust policy
without checking CloudTrail first wastes time chasing a document that
was never the problem.

## Verify
After identifying and narrowly adjusting the actual blocking policy
(SCP, boundary, or condition), re-run `aws iam simulate-principal-policy`
for the same action/resource and confirm it returns `allowed`, then have
the actual calling identity perform `sts:AssumeRole` for real and confirm
it succeeds. Check CloudTrail for the successful `AssumeRole` event to
confirm no other layer still produces a deny for this path.
