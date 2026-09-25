---
name: missing-network-policies-flat-pod-network
description: A compromised pod can reach any other pod or service in the cluster because no NetworkPolicy restricts east-west traffic beyond the default flat network.
triggers: ["can this pod talk to every other service in the cluster", "do we have network policies configured in kubernetes", "lateral movement possible between pods after compromise"]
permissions: ["READ"]
---

## Symptom
During a security review or after an incident where one compromised pod was used to probe or reach unrelated services, it's discovered that any pod in the cluster can initiate a network connection to any other pod or service, regardless of namespace or intended architecture boundaries. `kubectl get networkpolicy --all-namespaces` returns empty or covers only a handful of namespaces, confirming that Kubernetes' default flat, fully-open pod network is still in effect everywhere else.

## Likely causes
1. **No NetworkPolicy resources have ever been created**, and Kubernetes' default behavior with no policies present is to allow all ingress and egress between all pods -- this is a true default-open posture that requires explicit action to change, not a misconfiguration of some other setting.
2. **The cluster's CNI plugin doesn't actually enforce NetworkPolicy** even if some are defined -- some CNI plugins (certain basic/legacy configurations of Flannel, for instance) don't implement the NetworkPolicy API at all, so policies exist as inert YAML with zero runtime effect, giving false confidence.
3. **Namespace isolation was assumed to imply network isolation** -- teams often believe separating workloads into different namespaces provides network boundaries by default, when namespaces alone provide no network segmentation without policies explicitly scoping traffic.
4. **Policies were added for a few sensitive services (e.g. a database) but not applied cluster-wide as a default-deny baseline**, leaving most of the pod network still flat and only a small, inconsistent subset actually restricted.

## Diagnose
1. Confirm current policy coverage: `kubectl get networkpolicy --all-namespaces` -- an empty or sparse result relative to the number of namespaces/services confirms the gap.
2. Confirm the CNI plugin actually enforces policies at all: check the CNI in use (`kubectl get pods -n kube-system` for calico/cilium/weave/flannel pods) against that plugin's documented NetworkPolicy support -- this must be verified independently of whether policy YAML exists.
3. Empirically test lateral reachability: from a low-privilege test pod in one namespace, attempt to reach a service in an unrelated namespace it has no business talking to (`kubectl exec testpod -- curl -m 3 http://other-service.other-namespace.svc.cluster.local`) -- a successful connection where none should be architecturally possible confirms the flat-network risk directly.
4. Map actual required traffic flows (which services legitimately call which) using existing service mesh telemetry, application architecture docs, or traffic logs -- this is required before writing restrictive policies, since a network policy written without knowing real traffic patterns will either be too permissive (no real improvement) or break legitimate calls.

## Fix
Establish a default-deny baseline per namespace (a NetworkPolicy selecting all pods with no allowed ingress/egress), then add specific allow rules for each legitimate traffic flow identified during the mapping step -- typically scoped by namespace and pod label selectors (e.g. "pods labeled `app=api` may receive ingress only from pods labeled `app=frontend` in the same namespace, plus DNS and any required external egress"). Roll this out namespace by namespace starting with the highest-value targets (databases, internal admin services, anything holding sensitive data) rather than attempting a single cluster-wide cutover, since a broad default-deny applied all at once without validated allow-rules will break production traffic.

## Pitfalls
Writing a default-deny policy without an explicit DNS egress allow rule (typically to `kube-dns`/`coredns` on port 53) breaks service discovery for every pod in that namespace, since pods can no longer resolve service names even though the policy author only intended to restrict application traffic -- always include the DNS allow rule as a baseline alongside any default-deny policy, and test service-name resolution specifically after applying it.

## Verify
After applying default-deny plus scoped allow rules, repeat the earlier lateral-reachability test from an unrelated namespace and confirm the connection now times out or is refused. Then exercise the application's actual legitimate call paths end-to-end (not just individual services in isolation) to confirm the allow rules correctly permit every real traffic flow the mapping step identified, with no unexpected connection failures in application logs.
