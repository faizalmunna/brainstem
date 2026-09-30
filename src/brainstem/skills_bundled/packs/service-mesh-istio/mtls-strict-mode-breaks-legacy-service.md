---
name: mtls-strict-mode-breaks-legacy-service
description: Enabling strict mTLS mesh-wide breaks connectivity to a legacy service that can't participate in the mesh, causing silent connection failures instead of a clear error.
triggers: ["istio strict mtls breaks connection", "mesh wide mtls blocking legacy service", "peerauthentication strict connection refused", "mtls migration breaking traffic"]
permissions: ["READ"]
---

## Symptom

After enabling `STRICT` mTLS mode mesh-wide (or namespace-wide) via a
`PeerAuthentication` policy, traffic to or from a specific service starts
failing with connection resets or refused connections, and the failure
isn't obviously about certificates -- it just looks like the service
became unreachable.

## Likely causes

- **The target service isn't actually part of the mesh** (no sidecar
  injected -- see the related sidecar-injection skill in this pack) or
  is a legacy workload that can't run a sidecar at all (a VM, an external
  service, a workload on a different platform), so it has no way to
  participate in mTLS and strict mode rejects its plaintext connections
  outright.
- **A specific port on an otherwise-meshed service is used for a
  non-HTTP or non-mesh-aware protocol** that Istio doesn't automatically
  detect/wrap correctly, causing mTLS enforcement to apply somewhere it
  shouldn't or fail to negotiate properly for that specific port.
- **The strict policy was applied mesh-wide without first auditing which
  workloads could actually support it**, rolling out a blanket policy
  change without accounting for exceptions that existed for a reason
  (an external health-check system, a legacy monitoring agent).
- **A `DestinationRule` isn't configured to use Istio mTLS for callers of
  the affected service**, so even a properly-injected caller might still
  attempt a plaintext connection that a strict-mode destination now
  rejects.

## Diagnose

1. Identify the exact service/port combination experiencing failures and
   check whether it has an Envoy sidecar at all -- a non-meshed
   participant is the most common and clearest-cut cause.
2. Check the effective `PeerAuthentication` policy scope (mesh-wide,
   namespace, or workload-specific) and confirm exactly which workloads
   it applies `STRICT` mode to.
3. Check Envoy sidecar logs on both the caller and callee side for
   TLS-handshake-related errors, which distinguish an mTLS negotiation
   failure from an unrelated connectivity issue.
4. Check for any `PERMISSIVE`-mode exception that used to allow this
   specific legacy connection before the broader strict rollout, to
   confirm whether removing that exception is what caused the break.

## Fix

For workloads that genuinely can't participate in the mesh (external
services, VMs, unsidecar-able legacy systems), configure a scoped
`PeerAuthentication` exception (permissive mode for that specific
workload/port, or a properly configured mesh-external service entry with
appropriate TLS origination) rather than applying strict mode uniformly
and breaking them. Roll out strict mTLS incrementally -- start with
`PERMISSIVE` mode to observe what's actually meshed-and-compliant via
telemetry before flipping to `STRICT`, rather than jumping directly to
strict mesh-wide. Fix `DestinationRule` configuration for any caller that
needs to explicitly originate mTLS toward a strict-mode destination.

## Pitfalls

Don't respond to a legacy-service break by reverting to `PERMISSIVE`
mode mesh-wide -- that gives up the security benefit strict mode was
introducing for every other properly-meshed service, not just the one
exception; scope the permissive exception narrowly to the specific
workload that needs it. Also don't assume every connection failure after
an mTLS policy change is mTLS-related without checking Envoy logs first
-- an unrelated networking issue coinciding with the rollout can be
misdiagnosed and waste time chasing the wrong cause.

## Verify

After scoping the exception correctly, confirm the previously-broken
legacy service connection now succeeds, and confirm (via Istio's own
telemetry/`istioctl` policy-checking tools) that every other, properly-
meshed service-to-service connection is still enforcing strict mTLS as
intended -- the fix should be narrow, not a rollback of the whole policy.
