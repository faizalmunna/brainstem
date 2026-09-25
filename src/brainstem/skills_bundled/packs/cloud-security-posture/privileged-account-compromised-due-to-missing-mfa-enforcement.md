---
name: privileged-account-compromised-due-to-missing-mfa-enforcement
description: An admin or privileged cloud account is compromised via a leaked or phished password because multi-factor authentication was never actually enforced for it.
triggers: ["admin account compromised and had no mfa", "privileged user login without second factor", "why wasn't mfa required for that role", "phishing led to full account takeover no mfa"]
permissions: ["READ"]
---

## Symptom

After a compromise involving a privileged/admin cloud identity, the
post-incident review reveals that account never had multi-factor
authentication enforced -- a single leaked or phished password was
sufficient for full takeover. Often there was an org-wide MFA policy
"in place," yet this specific account fell outside its actual
enforcement scope.

## Likely causes

- **MFA is configured as encouraged/available but not enforced**, relying
  on individual users to opt in voluntarily, and privileged users --
  often the busiest, most senior people -- are exactly the ones who
  deprioritize enabling it themselves.
- **An MFA enforcement policy exists but has an exemption or exclusion
  group** (for break-glass accounts, service accounts converted to
  interactive use, legacy accounts predating the policy) and the
  compromised account fell into that exclusion without anyone tracking
  which accounts were exempted or why.
- **The account was provisioned outside the normal onboarding flow**
  (a contractor account, a federated identity from a newly acquired
  company, a directly-created cloud-provider-native account bypassing
  the primary identity provider) so it never passed through the
  process that would have enrolled it in MFA in the first place.
- **Conditional access / enforcement policy is scoped by group
  membership or role tag, and the compromised account's privileged
  access was granted through a path that didn't also add it to the
  MFA-enforced group** -- e.g. privilege was granted directly rather
  than through the role/group the policy actually targets.

## Diagnose

1. Pull the current MFA enrollment/enforcement status for every account
   holding privileged/admin roles across all identity providers and
   cloud-native identity stores in use (don't check only the primary
   SSO provider if cloud-native local accounts also exist).
2. Cross-reference the list of privileged role holders (query IAM/role
   bindings directly, not a stale access list) against the MFA
   enforcement policy's actual scope (which groups/conditional access
   rules it applies to) to find privileged accounts sitting outside that
   scope.
3. Check for any exemption or exclusion list on the MFA/conditional
   access policy and get explicit justification for each entry --
   flag any that no longer have a valid reason to be excluded.
4. Review the sign-in logs for the compromised account specifically to
   confirm the takeover login used only a password with no second
   factor challenge, establishing MFA absence (not an MFA bypass) as the
   actual failure mode.

## Fix

Enforce MFA at the policy level for anyone holding a privileged role,
using a mechanism tied to role/group membership so it's automatically
applied the moment privilege is granted rather than requiring a separate
manual enrollment step -- conditional access policies keyed to
privileged-role group membership, not individual account flags that can
be missed. Eliminate or tightly justify and time-bound any exemption
list, require phishing-resistant factors (hardware keys, platform
authenticators) specifically for the highest-privilege roles rather than
SMS/OTP alone, and include every identity source (cloud-native local
accounts, federated accounts from acquisitions, contractor accounts) in
enforcement scope, not just the primary SSO provider.

## Pitfalls

Don't consider MFA "handled" because an org-wide policy exists --
verify its actual enforcement scope against the actual current list of
privileged accounts, since role grants and policy scope drift apart over
time as people change roles and new accounts get created through paths
that bypass standard onboarding.

## Verify

Attempt (in a controlled test) a password-only sign-in against a test
account holding the same privileged role and confirm it is blocked
pending a second factor. Re-run the privileged-role-versus-MFA-scope
cross-reference and confirm zero privileged accounts fall outside
enforcement, then confirm the exemption list contains only justified,
time-bound entries with an explicit review date.
