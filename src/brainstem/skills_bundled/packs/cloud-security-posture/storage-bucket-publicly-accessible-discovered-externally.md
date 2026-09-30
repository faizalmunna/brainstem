---
name: storage-bucket-publicly-accessible-discovered-externally
description: An external researcher, scanner, or bug bounty report discloses that a storage bucket meant to be internal-only is publicly readable or listable.
triggers: ["bucket was public and we found out from a security researcher", "external scanner found open storage container", "bug bounty report of exposed s3 bucket", "objects publicly downloadable that should be private"]
permissions: ["READ"]
---

## Symptom

The first the team hears about a storage bucket or blob container being
world-readable is an inbound email from an external security researcher,
a scanner's public disclosure, or a bug bounty submission -- not an
internal alert. The bucket was never intended to be public; nobody
internally noticed because nothing was watching for this specific
condition.

## Likely causes

- **A bucket-level or object-level public-access setting was changed
  during a one-off task** (sharing a file with an external partner,
  testing a public download link) and never reverted once that task
  was done.
- **A default account/project-level setting allowing public access was
  never explicitly locked down**, so a bucket created later without
  anyone thinking about its ACL inherited a permissive default instead
  of a deliberately private one.
- **An overly broad bucket policy or ACL grants access to "any
  authenticated user" or a similarly broad principal**, which people
  mistake for "internal only" when it actually includes any account
  across the entire cloud provider, not just accounts within the
  organization.
- **Infrastructure-as-code defines the bucket correctly as private, but
  a manual console change during an incident or demo overrode it**, and
  because there's no drift detection, the manual change persisted
  silently after the original need passed.

## Diagnose

1. Enumerate every bucket/container in the account against the
   provider's public-access status field directly (e.g. AWS S3
   `PublicAccessBlock` configuration and bucket ACL/policy evaluation,
   GCS bucket IAM policy for `allUsers`/`allAuthenticatedUsers`, Azure
   Blob container public access level) -- don't rely on naming
   conventions or assumptions about which buckets "should" be private.
2. For any bucket flagged public, check its access logs for source IPs
   and user agents outside known internal ranges or CI systems, to
   establish how long it was actually being accessed externally, not
   just how long the setting existed.
3. Diff the live bucket configuration against its infrastructure-as-code
   definition (if one exists) to determine whether this was a drift
   event (console change bypassing IaC) or the resource was never
   IaC-managed at all.
4. Check the account/project's default public-access-block or
   organization-policy setting to determine whether new buckets inherit
   a safe default or would repeat this exposure the next time someone
   creates one without thinking about ACLs.

## Fix

Immediately apply the provider's account-level public-access block as
the default-deny baseline (AWS S3 Block Public Access at the account
level, GCS organization policy constraint disallowing public bucket IAM
bindings, Azure Storage account setting disabling public blob access),
so an individual bucket-level misconfiguration can no longer expose data
even if it recurs. Then remediate the specific bucket by removing the
public grant and re-provisioning it through infrastructure-as-code so
its intended state is codified and reviewable, not just fixed in the
console. Add continuous scanning (native posture tool or third-party)
that specifically checks for public storage exposure and alerts within
minutes of a change, closing the gap that let an external party find it
first.

## Pitfalls

Don't just flip the specific bucket back to private and consider the
incident closed -- if the account-level default still permits public
access and nothing scans for it, the exact same exposure will recur the
next time anyone (or any automation) touches that bucket's ACL, and
you'll be back to relying on an external party to notice.

## Verify

Confirm the account-level public-access-block setting is enabled and
that attempting to make a test bucket public via the console or CLI is
actively rejected. Run the continuous scanner against the previously
exposed bucket and confirm it now reports private status, then confirm
the same scanner would have caught the original exposure by checking its
finding history covers the exposure window (or, if newly deployed,
document that gap explicitly rather than assuming coverage).
