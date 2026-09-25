---
name: k8s-service-not-reachable
description: Diagnose a Kubernetes Service that returns connection refused/timeout even though its backing pods appear to be running.
triggers: ["kubernetes service unreachable", "connection refused kubernetes service", "service timeout k8s", "cant reach pod from service", "kubectl service not working"]
permissions: ["READ"]
---

## Symptom
Requests to a Kubernetes `Service` (from within the cluster, via
`ClusterIP`, or from outside via `LoadBalancer`/`Ingress`) time out or get
connection-refused, even though `kubectl get pods` shows the backing pods
as `Running`.

## Likely causes
1. **Service selector doesn't match the pod labels** -- a typo or a label
   change on the deployment that the Service's `selector` wasn't updated
   to match, so the Service has zero matching endpoints even though pods
   are running.
2. **Pod is `Running` but not actually `Ready`** -- a readiness probe
   failing means the pod is excluded from the Service's endpoints even
   though the process is up; `Running` and `Ready` are different things.
3. **Service `targetPort` doesn't match the container's actual listening
   port**, or the container isn't listening on the interface the cluster
   network expects (e.g. bound to `127.0.0.1` instead of `0.0.0.0`
   inside the container).
4. **NetworkPolicy blocking traffic** between the caller and the target
   pod, especially after a NetworkPolicy was added for security hardening
   without accounting for this specific traffic path.
5. **DNS resolution issue** -- calling the Service by a name that doesn't
   match its actual cluster-DNS name (wrong namespace, typo), especially
   common when calling cross-namespace without the full
   `service.namespace.svc.cluster.local` form.

## Diagnose
- `kubectl get endpoints <service-name>` -- if this is empty, the
  Service has no matching, ready pods; cross-check against
  `kubectl get pods --show-labels` and the Service's `spec.selector`.
- `kubectl describe pod <pod>` and check the `Ready` condition and any
  readiness probe failure events specifically, not just the pod phase.
- `kubectl exec` into another pod in the cluster and `curl`/`nc` the
  target pod's IP directly on the expected port (bypassing the Service)
  to isolate whether the problem is the Service layer or the
  application/pod itself.
- Check the container's actual listen address/port (app config or
  `netstat`/`ss` inside the container) against the Service's
  `targetPort`.
- If NetworkPolicies are in use, list them for the target namespace and
  check whether one would deny traffic from the caller's namespace/labels.

## Fix
- Correct the Service's `selector` (or the pod's labels) so they match
  exactly -- this is the most common root cause and the fastest to fix
  once confirmed via `get endpoints`.
- Fix the failing readiness probe (or its configuration) so healthy pods
  are correctly marked `Ready` and included in endpoints -- don't work
  around this by removing the readiness probe, since that removes real
  protection against routing traffic to a not-actually-ready pod.
- Align the Service's `targetPort` with the container's actual listening
  port, and ensure the application binds to `0.0.0.0` (or the pod's
  network namespace address) rather than `localhost`/`127.0.0.1` inside
  the container.
- Add an explicit `NetworkPolicy` allow rule for the specific legitimate
  traffic path if a policy is blocking it, rather than removing the
  policy entirely.
- For DNS issues, use the fully-qualified Service DNS name
  (`<service>.<namespace>.svc.cluster.local`) when calling across
  namespaces, and confirm via `nslookup`/`dig` from within a pod.

## Pitfalls
- Removing readiness probes or NetworkPolicies to "make it work" trades a
  real diagnosable configuration issue for a less-safe cluster
  (traffic routed to unready pods, or no network segmentation) --  fix
  the specific mismatch instead.
- Testing connectivity from outside the cluster when the actual failure
  is pod-to-pod (or vice versa) tests the wrong network path entirely --
  isolate which hop is actually failing (client -> Service, Service ->
  pod, or pod -> pod directly) before changing configuration.

## Verify
After the fix, `kubectl get endpoints <service-name>` should list the
expected pod IPs, and a request through the Service (not directly to a
pod IP) from the original caller should succeed consistently, not just
once.
