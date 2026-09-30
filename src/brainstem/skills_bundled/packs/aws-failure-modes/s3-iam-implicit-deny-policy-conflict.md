---
name: s3-iam-implicit-deny-policy-conflict
description: An S3 request is denied with access errors even though both the IAM identity policy and the bucket policy individually appear to allow the action.
triggers: ["s3 access denied but policy looks correct", "iam and bucket policy both allow but still denied", "s3 403 forbidden despite permissions", "s3 implicit deny", "bucket policy iam conflict"]
permissions: ["READ"]
---

## Symptom
A principal (IAM user, role, or Lambda execution role) gets `403
Forbidden` / `AccessDenied` on an S3 operation (`GetObject`, `PutObject`,
`ListBucket`) even though the caller can point to both an IAM identity
policy that allows the action and a bucket policy that also appears to
allow it -- neither policy in isolation looks like it should deny
anything.

## Likely causes
1. **An explicit `Deny` elsewhere always wins** -- a broader policy
   (a permissions boundary, an SCP at the AWS Organizations level, or
   another attached identity policy) contains an explicit `Deny` that
   overrides both allows; IAM evaluation is deny-overrides-allow across
   *all* applicable policies, not just the two the person is looking at.
2. **The bucket policy's `Principal` doesn't actually match the calling
   identity** -- e.g., it names an account ID or a specific role ARN, but
   the caller is assuming a *different* role, or is the same role
   reached via a different trust path (assumed-role session ARNs differ
   from the role ARN itself), so the bucket policy's allow simply never
   applies to this caller.
3. **Missing `s3:ListBucket` at the bucket-ARN level while
   `s3:GetObject` is granted at the object-ARN level** -- a very common
   split-permission mistake where reads of an already-known key succeed
   but any operation that requires listing (some SDK behaviors, console
   browsing) fails, and it's misread as "permissions are broken" broadly.
4. **The object was uploaded by a different AWS account/principal and
   retains that account's ownership**, and Object Ownership /
   bucket-owner-enforced settings aren't configured, so the bucket
   owner's IAM allow doesn't actually grant access to an object it
   doesn't own under the legacy ACL model.
5. **KMS key policy denies the caller** when the bucket uses SSE-KMS --
   S3 permissions alone are insufficient; the caller also needs
   `kms:Decrypt`/`kms:GenerateDataKey` on the specific CMK's key policy,
   which is a separate, easily-overlooked policy document.
6. **VPC endpoint policy scoping** -- if S3 is accessed via a VPC
   endpoint (Gateway or Interface) that has its own endpoint policy, that
   policy is evaluated too, and an overly narrow endpoint policy denies
   requests that both IAM and bucket policy would otherwise allow.

## Diagnose
- Use **IAM Policy Simulator** (or `aws iam simulate-principal-policy`)
  against the exact caller identity and exact action/resource to see
  which specific policy is producing the deny -- this directly names the
  offending statement instead of manual policy reading.
- Enable **S3 server access logging** or check **CloudTrail** for the
  denied request's `errorCode`/`errorMessage` -- CloudTrail often names
  which check failed (e.g., `explicit deny in an identity-based policy`
  vs. `explicit deny in a resource-based policy`).
- Run `aws organizations list-policies-for-target` (or check the
  console) for any SCP attached to the account/OU, and check for a
  permissions boundary on the IAM role/user
  (`GetRole`/`GetUser` shows `PermissionsBoundary`) -- both are easy to
  forget because they aren't attached to the resource or the obvious
  identity policy.
- Confirm the exact calling principal ARN (`aws sts get-caller-identity`)
  matches what the bucket policy's `Principal` block actually specifies,
  character for character, including whether it's the role ARN or an
  assumed-role session ARN.
- If SSE-KMS is in use, check the key policy
  (`aws kms get-key-policy`) for the caller's grant separately from the
  S3-side permissions.
- If accessed via a VPC endpoint, check the endpoint policy
  (`aws ec2 describe-vpc-endpoints`) for scoping that might exclude this
  bucket or action.

## Fix
Resolve conflicts by identifying and correcting the actual overriding
statement rather than adding more `Allow` statements on top -- an
explicit `Deny` anywhere in the evaluation set cannot be overridden by an
`Allow` elsewhere, so the fix is narrowing or removing the deny (in the
SCP, boundary, or bucket policy) once you've confirmed it's overly broad,
not adding redundant allows that will never take effect. For principal
mismatches, correct the bucket policy's `Principal` to the exact ARN
actually used at call time. For the list-vs-get split, grant
`s3:ListBucket` on the bucket ARN itself (not the object ARN) alongside
object-level actions on `bucket-arn/*`. For cross-account object
ownership, enable **S3 Object Ownership: Bucket owner enforced** so
ACLs are disabled and bucket-owner IAM/bucket policy is the sole access
control, eliminating the ACL-vs-policy split entirely. For KMS, add the
caller's principal to the key policy explicitly, or grant `kms:Decrypt`
via IAM if the key policy already delegates permission management to
IAM policies.

## Pitfalls
The default instinct of "add `"*"` to the bucket policy's principal or
action to make it work" both weakens security and often doesn't even fix
the issue, because an explicit deny elsewhere still wins regardless of
how broad the allow is -- broadening an allow can never override a deny.
Also, changing Object Ownership settings on a bucket with existing
ACL-based cross-account grants can suddenly change access for other
legitimate consumers, so audit existing ACLs before flipping to
bucket-owner-enforced.

## Verify
Re-run IAM Policy Simulator for the exact action/resource/principal after
the change and confirm it now returns `allowed`. Then perform the actual
failing operation as that principal (not as an admin) and confirm success,
checking CloudTrail for the corresponding `AccessDenied` event no longer
appearing for subsequent attempts in the same time window.
