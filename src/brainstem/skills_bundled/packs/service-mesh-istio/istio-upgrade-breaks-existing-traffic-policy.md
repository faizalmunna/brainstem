---
name: istio-upgrade-breaks-existing-traffic-policy
description: Upgrading the Istio control plane changes default behavior for an existing traffic policy, causing routing or security rules that worked before to behave differently with no application code change.
triggers: ["istio upgrade broke routing", "istio version upgrade changed behavior", "traffic policy different after istio upgrade", "istio api version deprecated breaking change"]
permissions: ["READ"]
---

## Symptom

After upgrading the Istio control plane to a new minor or major version,
an existing `VirtualService`, `DestinationRule`, `PeerAuthentication`, or
`AuthorizationPolicy` starts behaving differently -- routing takes a
different path, mTLS enforcement changes, or authorization decisions
differ -- despite no changes to the mesh configuration YAML itself.

## Likely causes

- **A newer Istio version changes a default value for an unspecified
  field** -- configuration that relied on an old implicit default now
  gets a different (safer, or simply different) default in the new
  version, changing behavior for any resource that didn't explicitly set
  that field.
- **An API version used by existing resources is deprecated or has
  different semantics in the new version** -- Istio's CRDs evolve across
  versions (e.g. `v1alpha3` to `v1beta1` transitions historically), and a
  resource still using an older API version might be interpreted with
  different defaults or partial compatibility shims.
- **A canary/revision-based upgrade leaves some sidecars on the old Istio
  proxy version while control-plane resources target the new version's
  semantics**, causing inconsistent behavior across the mesh during the
  migration window depending on which proxies have been upgraded.
- **A previously-undocumented or edge-case behavior that application
  configuration was implicitly relying on was fixed/changed as part of
  the upgrade**, and what looks like "Istio broke this" is actually
  "Istio corrected an inconsistency the config was accidentally depending
  on."

## Diagnose

1. Consult the specific Istio release notes/upgrade notes for the exact
   version jump made, specifically looking for "behavior change" or
   "default value change" entries related to the affected resource types.
2. Compare the affected resource's YAML for any field left unset that
   might have had a different implicit default in the old version versus
   the new one.
3. Check whether the cluster is mid-canary-upgrade (multiple Istio proxy
   revisions coexisting) and whether the specific affected workloads are
   on the old or new proxy version.
4. Use `istioctl analyze` (or the version-appropriate equivalent) to
   check for deprecation warnings or configuration issues flagged
   specifically in the context of the new version.

## Fix

Explicitly set any configuration field that previously relied on an
implicit default that changed, so behavior is deterministic regardless
of version-specific defaults going forward. Update resources still using
a deprecated API version to the current one, verifying semantics match
what's intended rather than assuming a straight conversion. For canary
upgrades, complete the proxy version rollout in a timely, monitored
fashion rather than leaving the mesh in a long-lived mixed-version state
where behavior can differ by workload.

## Pitfalls

Don't pin the Istio version indefinitely to avoid ever hitting an
upgrade-related behavior change -- that accumulates upgrade risk and
eventually forces a larger, riskier jump; instead, read release notes
for behavior changes proactively before each upgrade and test against a
non-production environment first. Also don't assume every post-upgrade
behavior difference is a bug to work around -- some are intentional
corrections, and the right fix may be updating configuration to the new,
more correct expectation rather than trying to restore old (possibly
unintentional) behavior.

## Verify

After making the identified configuration adjustments, confirm the
affected routing/security policy behaves as originally intended under
the new Istio version, and run `istioctl analyze` across the mesh to
confirm no other deprecation warnings or configuration issues remain
unaddressed from the same upgrade.
