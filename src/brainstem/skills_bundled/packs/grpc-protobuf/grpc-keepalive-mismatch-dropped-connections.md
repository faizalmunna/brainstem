---
name: grpc-keepalive-mismatch-dropped-connections
description: Idle gRPC connections get dropped or reset by an intermediary because client and server keepalive/ping settings do not agree with each other.
triggers: ["grpc connection reset idle", "grpc goaway enhance_your_calm", "keepalive ping mismatch grpc", "idle grpc connection dropped by load balancer", "grpc too_many_pings error"]
permissions: ["READ"]
---

## Symptom
gRPC calls fail intermittently after a period of low or no traffic on a
channel -- either with a connection reset, an `UNAVAILABLE` error on the
next call after idling, or (in the specific case of overly aggressive
client pinging) the server actively terminates the connection with a
`GOAWAY` frame carrying `ENHANCE_YOUR_CALM` / "too_many_pings." The
failure correlates with idle time or with a network device (load
balancer, NAT gateway, firewall) between client and server rather than
with any change in request logic.

## Likely causes
1. **An intermediary (cloud load balancer, NAT gateway, corporate
   firewall) silently closes TCP connections idle beyond its own timeout**
   (often shorter than either the client's or server's assumptions,
   commonly 60-350 seconds depending on the provider), and neither gRPC
   endpoint is sending HTTP/2 keepalive pings frequently enough to keep
   the connection registered as "active" from the intermediary's point of
   view.
2. **The client's keepalive ping interval is set far more aggressively
   than the server's configured minimum ping interval**, and the server
   (correctly, per its own configuration) considers this abusive and
   terminates the connection with `GOAWAY: too_many_pings`, especially
   when combined with `PERMIT_WITHOUT_CALLS` sending pings even with no
   active RPCs.
3. **Keepalive is configured on only one side** -- e.g. the server has a
   reasonable keepalive/idle policy but the client library's defaults
   don't send pings at all, so any intermediary with a shorter idle
   timeout than the server's own connection-idle setting drops the
   connection first, and the client only discovers this on its next call
   attempt.
4. **Keepalive time is set shorter than the round-trip time plus the
   configured keepalive timeout allows for**, under real-world network
   latency or transient congestion, causing the client to conclude the
   server is unresponsive and tear down a connection that was actually
   fine, producing spurious reconnects under load.

## Diagnose
- Reproduce with a deliberately idle channel: open a connection, make one
  call, then wait past the suspected idle window before making another,
  and observe whether it fails -- compare the failure timing against any
  known intermediary idle timeout (check the load balancer/NAT gateway's
  documented or configured idle timeout directly, don't guess).
  same problem, so isolate against a direct connection first if possible.
- Enable gRPC's HTTP/2-level tracing (`GRPC_VERBOSITY=DEBUG
  GRPC_TRACE=http,http_keepalive` in C-core-based stacks, or the
  language-specific equivalent) and inspect whether ping frames are being
  sent at all, at what interval, and whether a `GOAWAY` frame with a
  specific reason (e.g. `too_many_pings`) precedes the failure.
- Check both sides' explicit keepalive configuration side by side:
  client `keepalive_time`/`keepalive_timeout`/`keepalive_permit_without_calls`
  against server `MinTime`/`PermitWithoutStream` (naming varies by
  language) -- a client ping interval shorter than the server's minimum
  accepted interval is the specific signature of the `too_many_pings`
  failure mode.
- If behind a known cloud load balancer, check its documented maximum
  idle timeout for backend connections and compare it against both
  endpoints' keepalive ping interval -- the ping interval must be shorter
  than the intermediary's idle timeout, not just nonzero.

## Fix
- Set an explicit keepalive ping interval on the client shorter than the
  shortest idle timeout of any intermediary in the path (commonly
  something like every 30-60 seconds, tuned to the actual infrastructure
  rather than copied from an unrelated project), so the connection stays
  registered as active.
- Set the server's minimum-accepted-ping-interval (`grpc.keepalive_time`
  server option / `MinTime` in Go) to be equal to or looser than the
  client's configured ping interval, not stricter -- the two settings
  must be designed together, not independently defaulted.
- Enable keepalive pings even without active calls
  (`PermitWithoutStream`/`keepalive_permit_without_calls = true`) on
  channels that are expected to sit idle between bursts of traffic, since
  the default in most implementations only pings while a call is
  in-flight.
- Where the intermediary's idle timeout can be configured directly (a
  load balancer you control), prefer raising it to comfortably exceed
  realistic idle periods over relying solely on keepalive pings to paper
  over an aggressive timeout.

## Pitfalls
- Setting the client's ping interval very aggressively (e.g. every few
  seconds) "to be safe" -- this is exactly what triggers the server's
  `too_many_pings` protection and gets the connection killed outright,
  which is worse than the idle-drop problem it was meant to prevent.
- Fixing keepalive on the client only, after diagnosing a server-side
  `GOAWAY` -- both directions need settings that agree with each other;
  a good client setting paired with a stricter, unexamined server
  minimum still fails.
- Treating a keepalive fix as separate from connection retry/backoff
  logic -- even with correct keepalive settings, transient drops can
  still happen (network blips, backend restarts), so the client also
  needs to handle a dropped connection by transparently reconnecting and
  retrying the call, not surfacing a raw connection error to the caller.

## Verify
Hold a channel idle for longer than the previously observed failure
window (and longer than any known intermediary idle timeout) under the
new keepalive settings, then issue a call and confirm it succeeds on the
first attempt without a reconnect-triggered delay or error, and confirm
via HTTP/2-level logs that ping frames were exchanged at the expected
interval throughout the idle period with no `GOAWAY` from either side.
