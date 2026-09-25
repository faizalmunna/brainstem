---
name: encryption-at-rest-assumed-default-not-actually-enabled
description: A specific resource type turns out not to have encryption at rest configured because the team assumed it was on by default when it actually required explicit setup.
triggers: ["we assumed this was encrypted but it isn't", "compliance audit found unencrypted volume", "default encryption doesn't apply to this resource type", "encryption at rest was never actually turned on"]
permissions: ["READ"]
---

## Symptom

A compliance audit, customer security questionnaire, or incident
investigation reveals that a specific resource -- a database snapshot,
an attached disk volume, a specific storage tier, a backup archive --
has no encryption at rest actually configured. The team believed
encryption was handled automatically at the account or platform level,
but this particular resource type or creation path didn't inherit that
default.

## Likely causes

- **Encryption-at-rest defaults vary by resource type and even by
  creation method within the same provider** (a resource created via
  console might default differently than one created via a specific API
  call or older API version, and newer resource types often default to
  encrypted while legacy ones or specific derived artifacts like
  snapshots/backups do not automatically inherit the source's
  encryption setting).
- **A snapshot, backup, or exported copy of an encrypted resource was
  created without explicitly carrying forward the encryption
  configuration**, because copy/export/backup operations don't always
  default to preserving the source's encryption state, especially when
  moving across regions or accounts.
- **The team's mental model comes from one resource type's behavior
  (e.g., "our object storage is encrypted by default so everything must
  be") and was generalized incorrectly to a different resource type
  (disk volumes, message queues, cache stores) with different actual
  defaults.**
- **Infrastructure-as-code templates were written before the provider
  changed a default, or were copied from an older example**, so the
  code never explicitly sets the encryption parameter and silently
  relies on whatever the default happened to be at the time, which may
  differ from current provider defaults or may not be a safe default at
  all for that resource type.

## Diagnose

1. Enumerate every resource of the affected type (and adjacent types --
   snapshots, backups, read replicas, cross-region copies) across all
   accounts and directly query each one's actual encryption
   configuration field, rather than trusting an account-wide "default
   encryption enabled" setting to apply universally.
2. For each unencrypted resource found, trace its creation path (IaC
   module, manual console creation, an automated backup job, a
   cross-account/cross-region copy operation) to identify which specific
   path is producing unencrypted resources.
3. Check the infrastructure-as-code module or script responsible for
   that resource type for whether it explicitly sets an encryption
   parameter or omits it and relies on default behavior -- omission is
   the pattern to fix even for resources that happen to currently be
   encrypted, since default behavior can be provider-version-dependent.
4. Check whether any compliance framework or data classification policy
   the organization is subject to specifically requires encryption for
   this resource type, to properly prioritize remediation urgency.

## Fix

For each unencrypted resource, apply encryption explicitly -- which for
many resource types (e.g. existing unencrypted disk volumes or database
instances) requires creating an encrypted copy and migrating to it
rather than an in-place toggle, so plan for a migration window rather
than assuming a flag flip. Fix the root cause in infrastructure-as-code
by making encryption an explicit, required parameter in every module
that provisions the affected resource type (not relying on provider
defaults), and add a policy-as-code check (via the cloud provider's
policy engine or a third-party tool) that blocks provisioning of the
resource type without encryption explicitly set, so the gap can't
silently reappear through a future IaC change or a manual creation path.

## Pitfalls

Don't assume that because your primary/common resource types are
correctly encrypted, derived artifacts (snapshots, backups, cross-region
replicas, exports) of those same resources inherit that setting
automatically -- verify each derived artifact type's encryption
configuration independently, since copy/backup/replication operations
are a common place for the setting to silently not carry forward.

## Verify

Query every resource of the affected type across all accounts again and
confirm 100% report encryption enabled, including all snapshots, backups,
and cross-region/cross-account copies. Confirm the policy-as-code check
is active by attempting to provision a test resource of that type
without setting encryption and confirming the provisioning is blocked.
