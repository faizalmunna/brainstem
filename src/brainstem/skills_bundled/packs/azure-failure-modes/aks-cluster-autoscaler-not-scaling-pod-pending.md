---
name: aks-cluster-autoscaler-not-scaling-pod-pending
description: AKS pods stay stuck in Pending waiting for capacity because the cluster autoscaler is blocked by a misconfigured node pool constraint, not disabled outright.
triggers: ["aks pods pending no nodes available", "cluster autoscaler not adding nodes aks", "aks node pool max count reached silently", "aks pod unschedulable insufficient cpu"]
permissions: ["READ"]
---

## Symptom
Pods on an AKS cluster stay in `Pending` state with events like
`0/N nodes are available: insufficient cpu/memory` or
`FailedScheduling`, and no new nodes appear even though the cluster
autoscaler is enabled and the workload clearly needs more capacity. It
isn't that autoscaling was never turned on -- something is silently
preventing it from acting.

## Likely causes
1. **The node pool's `max-count` is already reached**, so the autoscaler
   is functioning correctly but has hit its configured ceiling -- this is
   easy to mistake for "autoscaler isn't working" when it's actually
   working exactly as configured, just configured with a ceiling too low
   for current demand.
2. **The pending pod's resource requests, node selector, or taint
   toleration can't be satisfied by any node pool's VM SKU or labels**,
   so the autoscaler correctly determines that adding another node of the
   available SKU(s) wouldn't actually let the pod schedule, and therefore
   doesn't scale up at all -- a distinct case from hitting max-count, since
   here it's a placement-eligibility problem, not a capacity-ceiling one.
3. **Regional VM SKU capacity/quota is exhausted** -- the autoscaler
   attempts to add a node but the underlying `Microsoft.Compute` quota for
   that VM size in that region/subscription is used up, or the specific
   SKU is temporarily unavailable in that region, so scale-up requests
   fail silently from the workload's perspective (visible only in cluster
   autoscaler logs or Activity Log, not in pod events).
4. **Pod Disruption Budgets or anti-affinity rules on a *different*
   workload prevent the autoscaler's own scale-down/rebalancing logic from
   consolidating nodes**, indirectly starving capacity for new pods even
   though it looks like a pure scale-up failure -- less common but worth
   ruling out when nodes exist but appear fragmented with unusable
   leftover capacity.
5. **The cluster autoscaler profile's scan interval or scale-up
   aggressiveness settings (`scan-interval`, `max-node-provision-time`)
   are tuned conservatively enough that scale-up lags far behind a sudden
   burst**, so pods sit pending for several minutes during legitimate
   in-progress scaling that looks stuck but isn't.

## Diagnose
- Run `kubectl describe pod <pod>` and read the exact `FailedScheduling`
  reason -- `insufficient cpu`/`memory` versus `node(s) didn't match node
  selector`/`didn't tolerate` point at capacity-ceiling versus
  placement-eligibility causes respectively.
- Check the node pool's current node count against its configured
  `--max-count` via `az aks nodepool show --query
  "[count,maxCount,enableAutoScaling]"` -- if `count` equals `maxCount`,
  the autoscaler is capped, not broken.
- Check cluster autoscaler logs (`kubectl logs -n kube-system -l
  app=cluster-autoscaler` if using the AKS-managed add-on's exposed logs,
  or the equivalent diagnostic setting) for explicit
  `scale.up.error.out.of.resources` or quota-related messages, which
  distinguish a quota/capacity problem from a scheduling-constraint
  problem.
- Check `az vm list-usage --location <region>` for the specific VM
  family/SKU used by the node pool to confirm whether subscription quota
  is actually exhausted.
- Review the pending pod's `nodeSelector`/`affinity`/`tolerations` against
  every node pool's labels and taints (`kubectl get nodes --show-labels`,
  `kubectl describe node <node> | grep Taints`) to confirm at least one
  node pool could, in principle, satisfy the pod if scaled up.

## Fix
Raise the node pool's `max-count` if the ceiling itself is the limiting
factor and the workload's demand is legitimate, treating max-count as a
deliberate cost/blast-radius control that needs periodic review against
actual usage rather than a "set once" value. For placement-eligibility
gaps, either adjust the pod's requests/selectors to match an existing node
pool's actual capabilities, or add a node pool with the SKU/labels/taints
the workload actually needs -- the autoscaler can only add more of what a
node pool is already defined to provide, it can't invent a new node pool
shape on demand. For quota exhaustion, request a quota increase for the
specific VM family/region ahead of anticipated growth, and consider
configuring the autoscaler with a secondary node pool using a different
VM SKU as a fallback so a single SKU's regional capacity constraints don't
fully block scaling. Tune `scan-interval` and related autoscaler profile
settings only after confirming the delay is genuinely the bottleneck, not
masking a capacity-ceiling or eligibility issue.

## Pitfalls
Setting `max-count` extremely high to "never hit the ceiling again"
removes a real safety control against runaway scale-out from a bug
(a crash-looping deployment endlessly requesting more replicas) turning
into a very large, very expensive node fleet -- size it to a realistic
peak with headroom, not to infinity. Also, adding node selectors/taints
to work around a placement problem without updating the autoscaler's
node pool definitions to match can create pods that *still* can't
schedule even after scale-up succeeds, because the new node's labels
don't match what was actually requested.

## Verify
Deliberately generate load that should trigger scale-up (deploy enough
replicas to exceed current capacity) and confirm via `kubectl get nodes
-w` that new nodes appear within the expected timeframe, and `kubectl get
pods` shows the previously pending pods transition to `Running`. Check
`az aks nodepool show` afterward to confirm the node count stayed within
the (possibly newly raised) max-count bound. Re-check cluster autoscaler
logs for the absence of quota or scheduling-constraint errors during the
test.
