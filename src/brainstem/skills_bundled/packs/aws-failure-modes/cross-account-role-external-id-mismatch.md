---
name: cross-account-role-external-id-mismatch
description: A cross-account IAM role assumption fails specifically due to an external ID that does not match what the trust policy requires.
triggers: ["assumerole external id mismatch", "cross account role assumption denied", "sts assumerole invalid external id", "third party role assumption failing", "cross account access denied external id"]
permissions: ["READ"]
---

## Symptom
An `sts:AssumeRole` call from one AWS account into a role in another
account fails with `AccessDenied`, specifically in a setup involving a
third party or a cross-account integration (a SaaS vendor, a CI/CD
system, an internal platform team's automation) where the trust policy
requires an `sts:ExternalId` condition -- and unlike a typical trust
policy mismatch, the principal ARN in the trust policy is confirmed
correct.

## Likely causes
1. **The external ID configured in the calling side's integration doesn't
   match the value in the target role's trust policy `Condition`
   (`sts:ExternalId`)** -- a simple value mismatch, often from the
   external ID being rotated on one side (e.g., regenerated in a SaaS
   vendor's dashboard) without updating the corresponding trust policy,
   or a typo/whitespace difference introduced when copy-pasting between
   systems.
2. **The external ID is being passed with different casing, leading/
   trailing whitespace, or through a templating system that URL-encodes
   or otherwise mangles it** before the actual `AssumeRole` API call,
   so what looks identical when eyeballed in two UIs is byte-for-byte
   different in the actual request.
3. **The trust policy's `Condition` uses `StringEquals` on
   `sts:ExternalId` correctly, but a *second*, unrelated condition in the
   same trust policy (e.g., an MFA requirement, an IP restriction, or an
   `aws:PrincipalOrgID`) is also failing**, and the external ID is
   incorrectly blamed because it's the most recently changed or most
   visible condition, when the actual failing condition is something
   else entirely.
4. **Multiple integrations/environments (staging vs. production) each
   have their own external ID, and the wrong one is being used** for a
   given target role -- e.g., a role meant for the vendor's production
   integration is being assumed using the staging integration's external
   ID because of a config mix-up.
5. **The external ID was never actually required to be static and secret
   by design intent, but was generated once and then regenerated/rotated
   by the third party as a routine security practice**, breaking the
   integration silently until both sides are updated in lockstep.

## Diagnose
- Check CloudTrail for the failed `AssumeRole` call's error detail --
  it typically states explicitly if the failure is due to `ExternalId`
  not matching, distinguishing it from a principal or other condition
  failure.
- Retrieve the exact external ID value from both sides independently
  (the target role's trust policy JSON via `aws iam get-role`, and the
  calling system's actual configured value, not a value someone
  remembers or a doc that might be stale) and diff them
  character-by-character, checking specifically for whitespace, case,
  and encoding differences.
- If the trust policy has multiple `Condition` keys, test each condition
  independently using IAM Policy Simulator, or temporarily (in a
  non-production test role) isolate the `ExternalId` condition alone to
  confirm whether it specifically is the failing one versus another
  condition in the same statement.
- Confirm which specific external ID is meant to correspond to which
  target role/environment if multiple integrations exist, by checking
  the third-party system's own documentation/dashboard for the
  environment-specific value it expects to be used.
- Check whether the external ID was recently rotated on either side by
  reviewing change history (CloudTrail `UpdateAssumeRolePolicy` events
  for the trust policy side, or the vendor's own audit log/changelog for
  their side).

## Fix
Update whichever side has the stale value so both the trust policy's
`sts:ExternalId` condition and the calling system's configured external
ID match exactly, treating the external ID as an opaque secret string
that must be copied verbatim (not retyped) between systems to avoid
transcription errors. Where the integration supports it, prefer letting
the third party generate and directly display the exact external ID
string in their own UI at the point of setup, and paste it directly into
the trust policy, rather than typing it manually from a support ticket or
email. For organizations managing multiple environments, name external
IDs distinctly per environment (e.g., include an environment tag in
internal documentation, even though the ID itself must match exactly what
the vendor expects) to avoid cross-environment mix-ups. If other
conditions in the same trust policy are also involved, fix them
independently and verify each condition in isolation rather than
assuming the external ID is the sole culprit just because it's the most
scrutinized part of a third-party trust policy.

## Pitfalls
Removing the `sts:ExternalId` condition entirely to unblock the
integration defeats its specific security purpose -- it exists to prevent
the "confused deputy" problem where a third party might be tricked into
assuming a role on behalf of an unintended customer, and removing it
across a multi-tenant vendor integration reopens exactly that risk.
Also, regenerating a *new* external ID on the target-role side as a "fix"
without confirming which side actually drifted can break other,
previously-working integrations that were relying on the old value being
stable.

## Verify
After aligning the external ID on both sides, have the actual
third-party/calling system perform a real `AssumeRole` call (not a
manually constructed test with a hand-typed external ID, since that
risks reintroducing the same transcription error) and confirm success via
CloudTrail showing the `AssumeRole` event with no error code. Confirm the
downstream operations the assumed role is meant to perform also succeed,
not just the assumption itself.
