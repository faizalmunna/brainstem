---
name: grpc-client-side-load-balancing-uneven
description: gRPC requests pile up on one or two backend instances while others sit nearly idle even though client-side load balancing is configured.
triggers: ["grpc load balancing not working", "uneven traffic across grpc pods", "one grpc backend overloaded others idle", "round robin not balancing grpc", "grpc all requests going to one pod"]
permissions: ["READ"]
---

## Symptom
A gRPC client is configured to load-balance across multiple backend
instances, yet metrics show requests concentrated heavily on one or two
instances while the rest receive little or no traffic -- often worsening
under load, with the hot instance showing high latency/CPU while siblings
sit idle. This is distinct from a single connection simply being slow;
the imbalance is specifically across which *instances* get picked.

## Likely causes
1. **The client is using a single long-lived HTTP/2 connection to one
   resolved address**, and gRPC by default multiplexes many RPCs over one
   connection rather than opening a new connection per call -- without an
   explicit client-side load-balancing policy, the client connects once
   (often to whatever the DNS resolver or a plain L4 load balancer in
   front of it happened to return) and every subsequent call reuses that
   same connection/backend for the life of the channel.
2. **The client's name resolver only returns a single address** (e.g.
   resolving a Kubernetes Service's ClusterIP instead of pod IPs via
   headless service DNS, or a load-balancer VIP) -- client-side balancing
   policies like `round_robin` can only distribute across addresses the
   resolver actually surfaces; if it surfaces one VIP, "round robin"
   round-robins across a list of one.
2. **`round_robin` (or another balancing policy) isn't actually
   configured** -- gRPC's default policy is `pick_first`, which picks one
   address from the resolved list and sticks with it for the connection's
   lifetime; without explicitly setting the channel's load-balancing
   policy, this is the default behavior even with multiple resolved
   addresses.
3. **A long-lived streaming RPC or a connection-pinning proxy in the path**
   holds one backend for a disproportionate share of total call volume --
   e.g. most traffic is actually a small number of very long streams, so
   per-call round robin doesn't help because the imbalance is in call
   *duration*, not call *count*.
4. **Uneven backend readiness/subsetting** -- the resolver includes
   addresses for instances that are still starting up or draining, and
   the balancing policy hasn't removed them from rotation yet (or health
   checking isn't wired in), so live traffic concentrates on whichever
   instances are currently marked ready.

## Diagnose
- Check the channel's actual resolved address list at runtime (enable
  gRPC's internal logging/tracing, e.g. `GRPC_VERBOSITY=DEBUG
  GRPC_TRACE=pick_first,round_robin` in C-core-based implementations, or
  the language equivalent) and confirm it lists multiple backend
  addresses, not one VIP/ClusterIP.
- Check the client channel construction code for an explicit
  service-config or load-balancing-policy setting
  (`grpc.WithDefaultServiceConfig('{"loadBalancingConfig":
  [{"round_robin":{}}]}')` or equivalent) -- absence of this means
  `pick_first` is in effect regardless of how many addresses resolve.
- Correlate per-backend request counts with call duration distribution --
  if a small number of backends are handling long-lived streams and the
  rest handle short unary calls, per-call round robin is working as
  designed and the imbalance is a workload-shape issue, not a
  configuration bug.
- Check whether the resolver is DNS-based against a headless Kubernetes
  Service (returns pod IPs) versus a normal Service (returns one
  ClusterIP) -- `kubectl get endpoints <service>` versus what the
  client's resolver target actually points at.

## Fix
- Point the client's resolver at something that returns the full set of
  backend addresses -- a headless Kubernetes Service (`clusterIP: None`)
  for DNS-based resolution, or an xDS-compatible service mesh/control
  plane for dynamic discovery -- rather than a single VIP that hides the
  backend topology from the client entirely.
- Explicitly set a load-balancing policy that fans out across the
  resolved addresses (`round_robin`, or a more advanced policy like
  `weighted_target` or `least_request` where supported) in the channel's
  service config, rather than relying on the `pick_first` default.
- Enable client-side health checking (or an xDS-based policy that
  respects backend health) so addresses for not-yet-ready or draining
  instances are excluded from the pick set instead of receiving traffic
  as soon as they resolve.
- For workloads dominated by a few long streams, balance at the
  *connection/stream* level deliberately (e.g. cap stream lifetime and
  force periodic reconnection so long streams eventually redistribute) or
  restructure into shorter-lived calls so the balancing unit matches the
  actual traffic shape.

## Pitfalls
- Putting a plain L4/TCP load balancer in front of backends and expecting
  it to balance gRPC traffic per-call -- L4 balancers balance
  *connections*, and since gRPC multiplexes many calls over one
  long-lived HTTP/2 connection, all calls on that connection stick to
  whichever backend the connection was established to, defeating the
  purpose; use an L7-aware proxy/mesh or client-side balancing instead.
- Switching to `round_robin` without also fixing the resolver -- round
  robin across a resolved list of one address changes nothing; the
  resolver and the balancing policy are two separate pieces that both
  need to be correct.
- Assuming even request *counts* per backend means the load is actually
  balanced -- if request cost varies widely (e.g. some calls stream large
  payloads), equal call counts can still mean very unequal CPU/memory
  load; balance on a cost-aware metric where request cost is uneven.

## Verify
With multiple backend instances running, issue a sustained burst of
individual unary calls from a single long-lived client channel and
confirm, via per-backend request counters or access logs, that calls are
distributed across all resolved instances in roughly the expected
proportion (not concentrated on one), then repeat after killing and
replacing one backend instance to confirm the client picks up the new
address set without requiring a client restart.
