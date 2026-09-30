---
name: secret-sprawl-across-multiple-uncoordinated-stores
description: An organization ends up with secrets scattered across Vault, cloud-provider secret managers, CI/CD variable stores, and config files, with no single source of truth or consistent rotation practice.
triggers: ["secrets scattered across multiple systems", "no single source of truth for secrets", "inconsistent secret rotation across teams", "secret sprawl audit finding"]
permissions: ["READ"]
---

## Symptom

A security audit or an attempt to rotate a widely-used credential reveals
that secrets for the organization's systems live across many
uncoordinated locations -- Vault for some services, a cloud provider's
native secret manager for others, CI/CD platform variables for build-time
secrets, and plain configuration files for older systems -- with no
consistent inventory of what exists where, and no consistent rotation
practice across them.

## Likely causes

- **Different teams adopted different secret storage solutions
  independently over time** based on whatever was convenient for their
  specific stack at the time (a cloud-native team using their cloud
  provider's secret manager, another team standardizing on Vault, CI/CD
  secrets living wherever the CI platform's own variable store put them),
  with no organization-wide standard ever established or enforced.
- **A migration to a centralized secret store (like Vault) was started but
  never completed**, leaving some systems migrated and others still on
  their original, disparate secret storage, with no clear plan or urgency
  to finish the migration.
- **No inventory or ownership tracking exists for secrets across the
  organization**, so nobody has a comprehensive view of what secrets
  exist, where they live, who owns them, and when they were last rotated
  -- discovering the full scope of secret sprawl typically only happens
  reactively, during an audit or incident.
- **Different secret stores have different rotation capabilities and
  practices**, so even where rotation policy exists on paper, its actual
  enforcement varies wildly depending on which store a given secret
  happens to live in.

## Diagnose

1. Attempt to build a comprehensive inventory of secret storage locations
   across the organization -- interview teams, scan configuration
   repositories for embedded credentials, and check every CI/CD
   platform's variable/secret store -- since no single query is likely to
   reveal the full scope.
2. For a sample of critical secrets, trace back to their actual storage
   location and last rotation date to gauge the real state of rotation
   discipline across different stores.
3. Assess which secret stores have genuine organizational ownership and
   monitoring versus which are effectively unowned/unmonitored
   (a departed team's CI variables, for instance).
4. Prioritize the inventory by risk -- which scattered secrets grant
   access to the most sensitive systems -- rather than trying to
   inventory everything with equal urgency.

## Fix

Establish (or recommit to) one designated organization-wide secret
management standard, and create a realistic, prioritized migration plan
moving the highest-risk scattered secrets first rather than attempting a
single big-bang migration. For secrets that must remain in a
platform-specific store for practical reasons (CI/CD platform secrets
that the platform itself needs direct access to), establish a consistent
rotation and ownership tracking practice for that store specifically,
rather than leaving it as an unmanaged exception. Build and maintain an
actual secret inventory (even a simple, manually-maintained one to start)
tracking what exists, where, who owns it, and rotation cadence.

## Pitfalls

Don't attempt to force an immediate, complete migration of every secret
to one central store without prioritizing by risk -- that's a large,
disruptive project that often stalls partway, leaving the organization in
a worse state (mid-migration, with some things moved and documentation
describing a target state that isn't actually reached). Prioritize
highest-risk secrets and accept a longer, phased migration timeline.

## Verify

After establishing the inventory and migration plan, confirm the
highest-risk previously-scattered secrets have been moved to the
designated standard store (or brought under a defined rotation/ownership
practice if they must remain elsewhere) and re-run the discovery process
periodically to confirm new secrets aren't being introduced into
uncoordinated storage going forward.
