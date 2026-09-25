---
name: vault-policy-too-broad-grants-excess-access
description: A Vault policy written with a wildcard path grants an application or user far more secret access than actually needed, discovered during a security review rather than by design.
triggers: ["vault policy too permissive", "vault wildcard path over-privileged", "security review found excess vault access", "vault least privilege violation"]
permissions: ["READ"]
---

## Symptom

A security review or audit of Vault access policies reveals that an
application's or team's policy grants access to a much broader set of
secret paths than that application/team actually uses -- often via a
wildcard pattern (`secret/data/*`) that was written for convenience
rather than scoped to actual need.

## Likely causes

- **A policy was written with a broad wildcard early in a project** (when
  the exact set of needed paths wasn't yet known, or to avoid repeatedly
  updating the policy as new secrets were added) and was never narrowed
  down later once actual usage patterns stabilized.
- **Multiple applications/services share a single Vault policy/role**
  for operational convenience, so the policy has to be broad enough to
  cover the union of all their needs, giving each individual service
  access to secrets only relevant to the others.
- **A policy was copy-pasted from a template or another team's policy**
  as a starting point and never actually tailored to the specific
  application's real secret access needs.
- **No process exists for periodically reviewing and narrowing policies**
  as applications evolve -- a policy that was reasonably scoped at
  creation time can become overly broad as the application's actual
  secret usage narrows or consolidates over time, with the policy never
  updated to match.

## Diagnose

1. Use Vault's audit log to determine the actual set of secret paths a
   given application/token has accessed over a representative period
   (weeks to months, to capture infrequent access patterns).
2. Compare the actual accessed path set against the policy's granted
   path set -- any path granted but never accessed is a candidate for
   removal.
3. For shared policies covering multiple applications, determine whether
   each application's actual needs are genuinely overlapping or whether
   they could be split into separate, more narrowly scoped policies/
   roles/tokens.
4. Check policy authorship history (when it was created/last modified)
   against how long the current secret access pattern has been stable, to
   gauge how stale a broad grant likely is.

## Fix

Rewrite policies to grant access only to the specific secret paths
actually used, based on real audit log data rather than guessing.
Split shared policies into per-application roles/tokens where
applications' actual needs diverge, even if it means more policies to
maintain, since the security benefit of least-privilege access outweighs
the administrative convenience of one broad shared policy. Establish a
periodic (e.g. quarterly) review process for access policies tied to
actual audit log usage, so scope narrows (or is at least reviewed) over
time rather than only ever growing.

## Pitfalls

Don't narrow a policy purely based on a short observation window that
might miss legitimate infrequent access (an application that reads a
specific secret only during a rare failover scenario, for instance) --
verify with the application owner before removing access to a path that
audit logs show as unused, in case it's a legitimate rarely-triggered
path rather than genuinely unnecessary. Also don't over-fragment
policies to the point of creating unmanageable administrative overhead --
balance granularity against practical maintainability.

## Verify

After narrowing a policy, monitor the application for any access-denied
errors related to Vault over a subsequent operational period (including
any known infrequent code paths) to confirm the narrowed policy still
covers everything genuinely needed. Re-run the audit-log-based analysis
periodically to confirm the policy stays aligned with actual usage over
time.
