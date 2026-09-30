---
name: authorizationpolicy-denies-legitimate-traffic
description: An Istio AuthorizationPolicy meant to restrict access to specific callers also blocks legitimate traffic that should be allowed, due to an incomplete or incorrectly scoped rule.
triggers: ["istio authorizationpolicy denying legitimate request", "rbac policy blocking valid traffic istio", "403 from istio authorization policy", "authorizationpolicy too restrictive"]
permissions: ["READ"]
---

## Symptom

After applying an `AuthorizationPolicy` intended to restrict a service to
only specific allowed callers, a legitimate caller that should be
permitted receives a `403 Forbidden` response at the mesh layer (visible
in Envoy access logs as `RBAC: access denied`), despite seemingly
matching the intended allow rule.

## Likely causes

- **The policy's `principals`/`source` matcher references an identity
  format that doesn't match the actual SPIFFE identity the caller
  presents** -- e.g. a mismatch in expected namespace, service account
  name, or trust domain in the identity string used in the rule.
- **The policy doesn't account for a caller that legitimately reaches the
  service through an intermediate hop** (a gateway, another service
  proxying the request), where the effective calling identity at the
  mesh layer is the intermediate service, not the original client, and
  the rule only allowlists the original client's identity.
- **Multiple `AuthorizationPolicy` resources apply to the same
  workload**, and Istio's evaluation semantics (deny policies take
  precedence over allow policies in specific combinations) produce an
  overall deny even though one individual allow rule looks like it should
  permit the request.
- **The policy's selector matches a broader or narrower set of workloads
  than intended** (a label selector mismatch), so the policy is
  enforced on the wrong workload, or an intended workload isn't covered
  by the allow rule at all, effectively falling to a default-deny stance
  if one exists.

## Diagnose

1. Check Envoy's access logs on the target workload for the specific
   RBAC denial and any additional detail about which principal was
   evaluated and rejected.
2. Compare the caller's actual mesh identity (via `istioctl` identity
   inspection tools, or from mTLS certificate details in Envoy debug
   logs) against exactly what the `AuthorizationPolicy`'s `principals`
   field expects.
3. Trace the actual network path the request takes -- confirm whether
   it goes directly from the intended caller, or through an intermediate
   proxy/gateway whose identity is what's actually presented to the
   target service.
4. List every `AuthorizationPolicy` applying to the target workload
   (by label selector) to check for conflicting or overlapping policies,
   not just the one that was most recently added.

## Fix

Correct the `principals`/`source` matcher to reflect the caller's actual
mesh identity exactly, including trust domain and namespace/service
account naming as actually presented. If traffic legitimately flows
through an intermediate hop, either allowlist that hop's identity
explicitly (if that's an acceptable trust boundary) or use Istio's
request-authentication/JWT-based identity propagation if the original
caller's identity needs to be preserved and checked at the final
destination. Consolidate multiple overlapping `AuthorizationPolicy`
resources for the same workload into a clearly understood, single source
of truth where practical, to avoid deny/allow precedence confusion.

## Pitfalls

Don't work around a denial by removing the `AuthorizationPolicy`
entirely or making it maximally permissive -- that defeats the purpose
of having mesh-level authorization at all; fix the specific identity
matching instead. Also don't assume the calling identity is always the
originating client -- in a multi-hop mesh, understanding exactly which
hop's identity is presented to the final destination is essential to
writing a correct policy.

## Verify

Retry the original legitimate request and confirm it now succeeds, and
confirm (with a deliberately different, genuinely unauthorized caller
identity) that the policy still correctly denies access -- proving the
fix was precisely scoped rather than accidentally opened up broadly.
