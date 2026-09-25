---
name: gateway-auth-gap-exposes-backend-directly
description: An endpoint assumed to be protected by the API gateway or reverse proxy is actually reachable unauthenticated because the gateway's routing or auth rule has a gap.
triggers: ["endpoint accessible without auth despite gateway protection", "internal API reachable directly bypassing gateway", "gateway auth rule not applied to route", "assumed protected endpoint turned out public"]
permissions: ["READ"]
---

## Symptom
A security scan, bug bounty report, or incident reveals that an endpoint the team believed required authentication -- because "the gateway handles auth" -- is actually reachable without any credentials, either through the gateway itself (a routing rule gap) or by hitting the backend service directly, bypassing the gateway entirely. The backend application code has no authentication check of its own because that responsibility was assumed to live entirely at the edge.

## Likely causes
1. **The backend service is reachable on a network path that doesn't go through the gateway** -- internal DNS, a direct load balancer, a Kubernetes service exposed on a NodePort, or a cloud load balancer with its own public IP that predates the gateway setup -- so the gateway's auth rules are simply never evaluated for traffic that takes that path.
2. **The gateway's route-matching rule has a gap for a specific path pattern** -- e.g. an auth rule applied to `/api/*` doesn't match `/api` (no trailing content) or a new endpoint was added at a path that doesn't match the existing glob/regex (a new `/v2/users` route added after the rule was written for `/v1/*` and `/api/*` only).
3. **A new service or route was added and the team assumed gateway-level auth would automatically apply**, when the gateway actually requires an explicit per-route policy attachment (common in API gateways like Kong, AWS API Gateway, or Envoy where auth is opt-in per route, not a global default).
4. **The backend genuinely has no defense-in-depth** -- it was built with the single assumption that only the gateway would ever call it, so even if the gateway gap is closed, the backend itself would still process any request it receives with no authentication of its own, meaning the gateway is the *only* control, not one layer of several.

## Diagnose
- Map the actual network topology: from outside the gateway, attempt to resolve and reach the backend service directly (internal DNS, direct load balancer hostname, container/pod IP if reachable) and check whether it responds without going through the gateway at all.
- Pull the gateway's route/policy configuration and diff it against the full list of backend endpoints (from the OpenAPI spec or route table) -- any backend route with no corresponding gateway policy entry is either unprotected or protected only by a default that may not be auth.
- For each gateway routing rule, test its exact match boundaries: trailing slashes, path parameters, case sensitivity, and newly added routes -- gateway glob/regex rules are a common source of "looks like it should match but doesn't" gaps.
- Check the backend application code directly: does it perform any authentication/authorization check of its own, or does every handler assume the caller is already authenticated because "that's the gateway's job"? A backend with zero independent auth checks has no defense-in-depth if the gateway is ever misconfigured, bypassed, or redeployed with a dropped rule.

## Fix
Treat the gateway as one layer, not the only layer, and make route protection explicit and verifiable:
- Add authentication/authorization checks in the backend service itself for any endpoint that isn't intentionally public, even if the gateway is also expected to enforce it -- defense-in-depth means a gateway misconfiguration degrades security rather than eliminating it entirely.
- Lock down network reachability so the backend genuinely cannot be reached except through the gateway (private subnets, security groups/network policies restricting ingress to only the gateway's IP/service identity, mutual TLS between gateway and backend) rather than relying on "nobody knows the direct URL" as security.
- Make gateway route policy attachment default-deny: new routes should require an explicit auth policy to be reachable at all, rather than defaulting to open until someone remembers to add a rule -- audit the gateway config for a catch-all "deny unless explicitly allowed" rule versus an "allow unless explicitly denied" posture.
- Add an automated check (in CI or a scheduled scan) that diffs the backend's actual route list against the gateway's configured policies and flags any backend route with no matching gateway rule.

## Pitfalls
Don't treat "add an auth check at the gateway" as sufficient remediation on its own -- if the backend remains network-reachable by any other path (which is how this gap was discovered in the first place), fixing only the gateway rule leaves the direct-access path exploitable. Both the network path and the policy gap need closing.

## Verify
From a network position outside the gateway (e.g. a host that isn't on the gateway's allowlisted path), attempt to reach the backend service directly and confirm the connection is refused or times out at the network layer; separately, send an unauthenticated request through the gateway to the previously-gapped route and confirm it now returns 401/403 rather than a successful response.
