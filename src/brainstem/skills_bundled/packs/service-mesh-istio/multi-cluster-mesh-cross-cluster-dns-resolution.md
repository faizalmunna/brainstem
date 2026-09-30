---
name: multi-cluster-mesh-cross-cluster-dns-resolution
description: A service in one cluster of a multi-cluster Istio mesh cannot reach a service in another cluster because cross-cluster service discovery or DNS resolution isn't correctly configured.
triggers: ["istio multi cluster service not found", "cross cluster mesh dns not resolving", "multi-cluster istio endpoint discovery failing", "east west gateway not routing"]
permissions: ["READ"]
---

## Symptom

In a multi-cluster Istio mesh deployment, a service in cluster A fails to
reach a service in cluster B that's supposed to be part of the same
mesh -- DNS resolution for the remote service's hostname fails, or
resolves but connections don't actually route to the remote cluster's
endpoints.

## Likely causes

- **The east-west gateway (used for cross-cluster traffic in a
  multi-network mesh topology) isn't correctly configured or reachable**
  between the two clusters, so even correctly resolved traffic has no
  path to actually cross cluster boundaries.
- **The remote cluster's secret/credentials weren't correctly registered
  in the local cluster's control plane** (for a multi-primary or
  primary-remote topology), so the local cluster's Istio control plane
  has no visibility into the remote cluster's service registry at all.
- **Cross-cluster service discovery is enabled, but the specific
  service's Kubernetes `Service` object doesn't have the expected
  multi-cluster-aware labels/annotations**, so it's not exposed for
  cross-cluster discovery even though the mesh-level plumbing is
  otherwise correctly set up.
- **Network-level connectivity between clusters isn't actually
  established** (firewall rules, VPC peering, or equivalent network
  path) independent of any Istio configuration, causing failures that
  look like a mesh configuration issue but are actually infrastructure-
  level.

## Diagnose

1. Check whether the local cluster's Istio control plane has the remote
   cluster registered (via `istioctl` multi-cluster status commands or
   equivalent), confirming basic control-plane-level awareness exists.
2. Check the east-west gateway's status and configuration in both
   clusters, and test basic network connectivity between the gateways
   directly (independent of application-level service calls).
3. Check the target service's labels/annotations for whatever the
   specific multi-cluster topology in use requires for cross-cluster
   exposure.
4. Isolate whether the failure is DNS resolution (the hostname doesn't
   resolve at all) versus routing (it resolves but the connection fails),
   since these point at different layers of the multi-cluster setup.

## Fix

Correctly register each cluster's credentials/secrets with the others'
control planes according to the specific multi-cluster topology in use
(primary-remote, multi-primary), verify east-west gateway configuration
and underlying network connectivity between clusters independently of
Istio configuration, and ensure services intended for cross-cluster
exposure have the labels/configuration the specific topology requires.
Test network-level connectivity between clusters as a prerequisite check
before troubleshooting mesh-level configuration, since a network-layer
gap will make any mesh configuration fix ineffective.

## Pitfalls

Don't assume a single-cluster mesh troubleshooting approach transfers
directly to multi-cluster issues -- the additional layers (cross-cluster
control plane registration, east-west gateways, network-level
connectivity between clusters) each introduce their own distinct failure
points that don't exist in a single-cluster setup. Also don't skip
verifying basic network connectivity between clusters first, since
debugging mesh-level configuration extensively while a more fundamental
network path is broken wastes significant time.

## Verify

Confirm DNS resolution for the remote service's hostname succeeds from
within the local cluster, and confirm an actual test connection reaches
and gets a response from the remote cluster's service instance
specifically (not a local cluster instance, if a service happens to
exist in both, which can otherwise mask a false verification).
