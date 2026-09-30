---
name: missing-sticky-sessions-breaks-websocket-load-balancing
description: WebSocket connections fail or behave inconsistently behind a load balancer because sticky session affinity was never actually configured for the upgrade and follow-on requests.
triggers: ["websocket connection fails intermittently behind load balancer", "works with one instance but not multiple", "handshake succeeds but connection drops immediately", "sticky sessions not working", "load balancer routes websocket requests to different servers"]
permissions: ["READ"]
---

## Symptom
WebSocket connections work reliably against a single backend instance
but become flaky, fail the upgrade handshake intermittently, or
connect successfully yet immediately behave as if the server has no
memory of the client (missing subscriptions, "session not found"
errors, silent disconnects) once the service is scaled to multiple
instances behind a load balancer. The failure rate roughly tracks
instance count -- more backend instances means a higher chance any
given request in a multi-request flow lands somewhere inconsistent.

## Likely causes
1. **The load balancer has no session affinity configured at all**,
   so it round-robins or least-connections-balances every request
   independently -- if the WebSocket protocol or application relies on
   more than the single initial upgrade request reaching the same
   backend (e.g. a preceding auth/handshake HTTP call, or reconnect
   logic that treats reconnection as a fresh request the LB may route
   anywhere), those requests can land on a different instance than the
   one holding relevant server-side state.
2. **Affinity is configured using a mechanism the client doesn't
   actually preserve** -- cookie-based stickiness when the WebSocket
   client (a mobile app, a non-browser client) doesn't send cookies at
   all, or IP-based affinity behind a NAT/corporate proxy where many
   distinct users share one apparent source IP, silently defeating the
   affinity mechanism for exactly the clients it was meant to help.
3. **Affinity is configured at a layer that doesn't see the actual
   WebSocket traffic** -- e.g. configured on an HTTP-level load
   balancer or ingress rule that only applies to a listener/path the
   WebSocket upgrade doesn't actually go through, so it silently has
   no effect on the traffic that matters even though it looks
   correctly configured on paper.
4. **The application was actually designed to be stateless across
   instances (session state lives in a shared store or is
   reconstructed via the fan-out layer) but sticky sessions were added
   anyway "to be safe," or vice versa** -- a mismatch between the
   architecture's actual statefulness assumption and what's configured
   causes either unnecessary hotspotting (true statelessness, but
   traffic pinned anyway) or real failures (real per-instance state,
   but no pinning), and the fix differs completely depending on which
   mismatch this is.

## Diagnose
- Confirm which layer originates the affinity decision (a cloud load
  balancer's target group setting, an ingress controller annotation, a
  reverse proxy's `upstream` hash directive) and check specifically
  whether it's applied to the listener/path that actually carries the
  WebSocket upgrade request, not just the general HTTP path.
- Reproduce with instance-identifying logging: have each backend
  instance log its own identity on every request/connection it
  handles, then drive a client through a full connect-then-reconnect
  cycle and confirm whether the same instance ID appears throughout,
  or changes between the initial handshake and subsequent requests.
- Check what the affinity mechanism actually keys on (cookie, source
  IP, a custom header) and verify the client in question actually
  sends that key consistently -- inspect real request headers from a
  representative client (not just a browser test) for the expected
  cookie or header.
- Determine whether the application genuinely needs affinity by
  checking where per-connection state actually lives: if all relevant
  state (subscriptions, session data) is already externalized to a
  shared store or reconstructed via the fan-out layer on any instance,
  affinity may be an unnecessary constraint rather than a missing
  requirement -- confirm this before assuming the fix is "add
  stickiness."
- Check load distribution across instances during normal operation --
  a suspiciously uneven distribution can indicate affinity is
  technically working but pinning too coarsely (e.g. by IP, collapsing
  many users onto few instances), which is a different problem from
  affinity being entirely absent.

## Fix
Match the load balancing configuration to the application's actual
statefulness, and configure it at the layer that actually sees
WebSocket traffic:
- If per-connection server-side state genuinely isn't externalized,
  configure session affinity explicitly at the layer handling the
  WebSocket upgrade (e.g. the correct listener/target group, not a
  same-named but different HTTP path), using a key the actual client
  population reliably provides -- prefer an application-level token/
  header the client controls over source IP, which is unreliable
  behind shared-IP NATs and proxies.
- Prefer designing new WebSocket services to be stateless across
  instances in the first place -- externalize session/subscription
  state to a shared store or reconstruct it via the fan-out layer on
  whichever instance a connection lands on -- since this eliminates
  the entire class of affinity-misconfiguration failures rather than
  requiring the load balancer to get a subtle setting exactly right
  forever.
- Where affinity is required, verify it end-to-end through an actual
  WebSocket client in a staging environment with multiple instances,
  not just by reading the load balancer's configuration -- a setting
  that looks correct can still not apply to the real traffic path, as
  in cause 3 above.
- Document the chosen approach (stateless-via-shared-store vs.
  sticky-with-affinity) explicitly near the load balancer config and
  the connection-handling code, since this is exactly the kind of
  cross-cutting assumption that silently rots when one side changes
  without the other during a later refactor.

## Pitfalls
- Adding sticky sessions as a quick fix for an intermittent failure
  without first determining whether the architecture assumes
  statelessness can mask a real bug (state that should have been
  externalized but wasn't) behind a load balancer setting, so the
  underlying design debt resurfaces the next time the affinity
  mechanism doesn't apply cleanly (a new CDN/proxy hop added in front,
  a client that doesn't preserve cookies).
- Configuring cookie-based affinity as the only mechanism without a
  fallback for clients that don't send cookies (native mobile clients,
  some non-browser SDKs) fixes the problem for browser clients while
  leaving exactly the clients most likely to be on this pack's other
  failure modes (flaky mobile networks) still unpinned.
- Assuming sticky sessions alone solve reconnection correctness --
  affinity only controls *routing*, not what happens to server-side
  state when the pinned instance itself restarts or is drained (see
  this pack's connection-draining skill), so affinity and graceful
  reconnection/resync need to be solved together, not treated as the
  same fix.

## Verify
With at least two backend instances running, drive a real WebSocket
client (not just a browser dev-tools test) through connect, an
action that depends on server-side per-connection state, a simulated
network blip, and reconnect -- confirming via per-instance identity
logging that every request in that flow reaches the same instance
when affinity is required, and that the client's action succeeds
correctly rather than hitting a "session not found" or silent-failure
path on any request that lands elsewhere.
