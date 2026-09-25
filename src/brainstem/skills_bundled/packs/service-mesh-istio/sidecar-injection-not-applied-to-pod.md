---
name: sidecar-injection-not-applied-to-pod
description: A pod deployed into an Istio-enabled namespace runs without the Envoy sidecar, silently bypassing all mesh traffic policy and observability for that pod.
triggers: ["istio sidecar not injected", "envoy proxy missing from pod", "istio mesh policy not applying to a pod", "sidecar injection not working"]
permissions: ["READ"]
---

## Symptom

A pod runs in a namespace that's supposed to be part of the Istio mesh,
but inspecting the pod shows only the application container, no Envoy
sidecar container -- traffic to/from that pod bypasses mTLS, traffic
policy, and mesh telemetry entirely, often discovered only when a policy
that should apply clearly isn't taking effect.

## Likely causes

- **The namespace isn't actually labeled for automatic sidecar
  injection** (`istio-injection=enabled`, or the revision-specific label
  for newer Istio versions), so the mutating webhook that adds the
  sidecar never triggers for pods in that namespace.
- **The pod's own spec explicitly opts out of injection** via an
  annotation (`sidecar.istio.io/inject: "false"`), possibly left over
  from earlier debugging or copied from a template not meant for mesh
  traffic.
- **The pod was created before the namespace label was applied**, since
  injection happens at pod creation time via the admission webhook --
  existing pods don't retroactively get a sidecar just because the
  namespace label changed afterward; they need to be recreated.
- **The Istio injection webhook itself is misconfigured or not running**
  (a broader control-plane issue affecting the whole cluster, not just
  one namespace/pod), which is a different, more systemic cause worth
  ruling in or out early.

## Diagnose

1. Check the namespace's labels for the expected injection-enabling
   label, and compare against what the cluster's Istio installation
   actually expects (label name/value can differ by Istio version/
   revision-based upgrade setup).
2. Check the specific pod's own annotations for an explicit
   injection-disabling override.
3. Check the pod's actual creation timestamp relative to when the
   namespace label was applied -- if the pod predates the label, that's
   the direct explanation, independent of any other misconfiguration.
4. If neither explains it, check the cluster-wide Istio injection webhook
   (`kubectl get mutatingwebhookconfiguration`) for whether it's present,
   correctly configured, and its underlying service is healthy.

## Fix

Apply the correct injection-enabling label to the namespace, and
recreate any pods that existed before the label was applied (a rollout
restart of their deployment is sufficient, since injection happens at
pod creation). Remove any explicit injection-disabling annotation left
on pod specs that are actually meant to be part of the mesh. If the
control-plane webhook itself is the issue, that's a cluster-level Istio
installation problem needing its own investigation, separate from any
individual namespace/pod configuration.

## Pitfalls

Don't assume relabeling the namespace alone is sufficient -- forgetting
to recreate already-running pods is the most common miss here, and it's
easy to declare the fix "done" after just changing the label while
existing pods silently continue running without a sidecar. Also
distinguish intentionally injection-excluded workloads (some
infrastructure pods are deliberately excluded from the mesh) from
accidentally excluded ones before blanket-enabling injection everywhere.

## Verify

After the fix, list the pod's containers and confirm the Envoy sidecar
container is now present and running. Confirm a mesh-level policy that
previously had no effect (an mTLS requirement, a traffic-shaping rule)
now actually applies to traffic involving this pod.
