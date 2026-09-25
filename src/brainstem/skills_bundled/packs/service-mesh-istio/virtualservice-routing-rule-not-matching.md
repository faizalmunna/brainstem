---
name: virtualservice-routing-rule-not-matching
description: An Istio VirtualService routing rule intended to split or redirect traffic never actually applies, and traffic keeps hitting the default destination instead.
triggers: ["istio virtualservice not matching", "traffic split not working istio", "virtualservice rule ignored", "istio canary routing not applying"]
permissions: ["READ"]
---

## Symptom

An Istio `VirtualService` configured to route a percentage of traffic to
a new version, or to match specific requests (a header, a path) and
route them differently, has no observable effect -- all traffic continues
to hit the default/original destination as if the rule doesn't exist.

## Likely causes

- **The `VirtualService`'s `hosts` field doesn't match how clients
  actually address the service** (a short name versus a fully-qualified
  domain name, or a mismatch with the `Gateway` it's meant to attach to
  for ingress traffic), so Envoy never applies the rule to the traffic in
  question.
- **A conflicting or higher-precedence `VirtualService` for the same host
  exists elsewhere** (Istio merges/prioritizes rules in ways that can be
  non-obvious with multiple `VirtualService` resources targeting
  overlapping hosts), effectively shadowing the intended rule.
- **The `DestinationRule` referenced by the `VirtualService`'s subset
  labels doesn't actually match any pods** (a label selector typo, pods
  not labeled with the expected version), so the subset-based routing
  has nothing valid to route to and falls back to default behavior.
- **The calling service doesn't have a sidecar**, or its sidecar's
  configuration hasn't yet propagated the updated routing rule (Istio
  control-plane config propagation isn't instantaneous, and a very
  recent change might not have reached every proxy yet).

## Diagnose

1. Confirm the exact host(s) declared in the `VirtualService` match
   exactly how the client actually calls the service (check the request's
   actual `Host`/`:authority` header against the configured hosts).
2. List all `VirtualService` resources for the same host across
   namespaces to check for a conflicting or overlapping rule taking
   precedence.
3. Check the `DestinationRule`'s subset label selectors against the
   actual labels on the target pods (`kubectl get pods --show-labels`)
   to confirm the subsets resolve to real, matching pods.
4. Use `istioctl proxy-config routes <pod>` (or equivalent) on the
   calling pod's sidecar to inspect the actual routing configuration
   Envoy has received, confirming whether the intended rule has
   propagated and is present at the proxy level.

## Fix

Correct the `VirtualService` host(s) to exactly match real client
traffic, resolve any conflicting overlapping `VirtualService` definitions
for the same host (consolidating into one clearly-owned resource per
host where practical), and fix `DestinationRule` subset label selectors
to match actual pod labels. If propagation delay is suspected, allow a
brief window and re-check via `istioctl proxy-config` rather than
assuming the control plane failed.

## Pitfalls

Don't create multiple, independently-owned `VirtualService` resources for
the same host across different teams/directories without a clear
ownership and precedence convention -- this is a common source of
confusing, hard-to-debug routing conflicts as an organization scales its
mesh usage. Also don't assume a routing rule applies globally just
because it was applied cluster-wide -- Istio's sidecar-based enforcement
means the *calling* service's sidecar configuration is what actually
matters for outbound routing decisions.

## Verify

Send a test request matching the intended routing condition (the right
header, the right path, or simply enough requests to statistically
confirm a percentage split) and confirm it's routed to the intended
destination/subset. Use `istioctl proxy-config routes` on the calling
sidecar to directly confirm the expected routing rule is present and
correctly configured at the proxy level, not just assumed from the
applied YAML.
