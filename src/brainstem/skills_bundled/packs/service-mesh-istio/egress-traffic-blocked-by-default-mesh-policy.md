---
name: egress-traffic-blocked-by-default-mesh-policy
description: A service inside the mesh cannot reach an external API or database because Istio's default outbound traffic policy blocks egress to hosts not explicitly registered.
triggers: ["istio blocking external api call", "egress traffic denied mesh", "cannot reach external service from mesh", "outboundtrafficpolicy registry only blocking"]
permissions: ["READ"]
---

## Symptom

A service running inside the mesh fails to connect to an external
(outside-the-mesh) API, database, or third-party service -- connection
attempts fail or time out -- despite the same external endpoint being
reachable from outside the mesh (a local machine, a non-meshed pod)
using the same network path and credentials.

## Likely causes

- **The mesh's outbound traffic policy is set to `REGISTRY_ONLY`**
  (a common secure-by-default configuration) which blocks any outbound
  traffic to hosts not explicitly declared via a `ServiceEntry`, and the
  external host in question was never registered.
- **A `ServiceEntry` exists for the external host but with an incorrect
  port, protocol, or hostname** (a typo, a mismatch between the exact
  hostname used in application code versus what's registered) that
  doesn't match the actual outbound request.
- **TLS origination for the external service is misconfigured** -- the
  `ServiceEntry` and associated `DestinationRule` don't correctly set up
  TLS origination for an HTTPS external endpoint, causing a
  protocol-level failure that looks like a generic connection failure.
- **The failure is intermittent because only some outbound paths are
  registered** (an external service with multiple IPs/hostnames behind a
  load balancer or CDN, where only one specific endpoint was registered),
  so some legitimate traffic succeeds while other equally legitimate
  traffic to the same logical service fails.

## Diagnose

1. Check the mesh's configured `outboundTrafficPolicy` mode
   (`ALLOW_ANY` vs `REGISTRY_ONLY`) at the mesh or namespace level to
   confirm whether registry-only enforcement is actually in effect.
2. If in `REGISTRY_ONLY` mode, check for an existing `ServiceEntry`
   matching the exact external host, port, and protocol the application
   is trying to reach.
3. Check Envoy sidecar logs on the calling pod for the specific
   connection attempt and its failure reason, which usually distinguishes
   a policy-blocked connection from a genuine network-level failure.
4. If a `ServiceEntry` exists but access still fails, check the
   associated `DestinationRule`'s TLS settings for correctness against
   what the external endpoint actually requires.

## Fix

Add a `ServiceEntry` (and, for HTTPS endpoints, a matching
`DestinationRule` configuring appropriate TLS origination) explicitly
registering the external host(s), ports, and protocols the application
legitimately needs to reach, keeping the mesh's `REGISTRY_ONLY` policy
intact rather than switching to `ALLOW_ANY` mesh-wide. For external
services with multiple backing hosts/IPs, ensure the `ServiceEntry`
covers the full legitimate set (a wildcard host pattern where
appropriate, or explicit enumeration) rather than just the first
endpoint discovered during initial testing.

## Pitfalls

Don't switch the mesh's outbound policy to `ALLOW_ANY` as a quick fix --
`REGISTRY_ONLY` is a meaningful security control limiting what external
destinations meshed services can reach, and disabling it mesh-wide gives
up that protection for every service, not just the one that needed
access. Scope the fix to registering the specific needed destination(s)
instead.

## Verify

Confirm the application's outbound call to the external service now
succeeds from within the mesh. Confirm a genuinely unregistered,
unrelated external host is still correctly blocked, proving the fix
was scoped to the specific needed destination rather than an accidental
broader policy relaxation.
