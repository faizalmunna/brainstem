---
name: silently-dropped-connection-with-no-heartbeat-detection
description: A WebSocket connection appears open on the client but was actually dropped by an intermediate proxy or load balancer, silently losing messages with no heartbeat to detect it.
triggers: ["connection shows open but no messages arrive", "client thinks it's connected but isn't", "messages silently lost over websocket", "idle timeout drops connection without a close event", "zombie websocket connection"]
permissions: ["READ"]
---

## Symptom
A client's WebSocket reports `readyState === OPEN` (or the equivalent
"connected" state) and no `close` or `error` event ever fires, yet no
messages arrive from the server for an extended period even though the
server believes it's still sending to that client -- or, conversely,
the server believes a client disconnected long before the client's own
state reflects it. The pattern correlates with connections that sit
idle (no traffic in either direction) for a while, and often
specifically with clients behind particular corporate proxies, mobile
carrier NATs, or certain load balancer configurations, rather than
happening to every client uniformly.

## Likely causes
1. **An intermediate NAT, proxy, or load balancer silently times out
   and drops idle TCP connections** after a period of no traffic
   (common defaults are anywhere from 60 seconds to a few minutes),
   without sending a TCP FIN/RST that either endpoint's OS-level
   socket would surface as a close -- both client and server's
   application-level WebSocket object continue believing the
   connection is open because nothing told them otherwise.
2. **No ping/pong heartbeat is implemented at the application or
   WebSocket-protocol level**, so there's no mechanism for either side
   to actively verify the other is still reachable during idle
   periods -- the connection's actual liveness is only ever discovered
   passively, whenever the next real message happens to be sent and
   fails.
3. **A heartbeat exists but only in one direction, or is answered by
   an intermediary rather than the true endpoint** -- e.g. a load
   balancer or proxy that terminates the TCP connection and answers
   low-level keepalives itself while the actual backend has already
   died, or a client that sends pings but never checks for a
   corresponding pong before assuming liveness, making the heartbeat
   only prove reachability to the wrong hop.
4. **The heartbeat interval is longer than the intermediary's idle
   timeout**, so pings are still being sent "eventually" but not often
   enough to keep the underlying TCP connection classified as active
   from the intermediary's point of view, letting it get reaped
   between heartbeats anyway.

## Diagnose
- Check whether the application implements WebSocket ping/pong frames
  (the protocol-level control frames, distinct from an
  application-level "heartbeat" JSON message) and at what interval --
  absence of any ping/pong is the first thing to confirm.
- Reproduce by opening a connection and leaving it genuinely idle (no
  app traffic) behind the same network path production clients use,
  for longer than any suspected intermediary timeout, then attempt to
  send a message from the server -- if it fails or never arrives while
  the client's `readyState` still reports open, that confirms a
  silent drop.
- Check known idle-timeout defaults for every hop in the actual path
  (cloud load balancer idle timeout, reverse proxy `proxy_read_timeout`/
  `proxy_send_timeout`, corporate/mobile NAT typical values) and
  compare the shortest of them against the application's current
  heartbeat interval, if any.
- If pings are implemented, verify pongs are actually being checked
  against a deadline (not just sent-and-forgotten) -- log missed pongs
  and confirm the server actively closes a connection that misses N
  consecutive pongs, rather than only reacting to a future failed
  send.
- Capture packets (or LB/proxy access logs) during a reproduction to
  see which hop actually closed the TCP connection and when, versus
  when the application first noticed -- a large gap between the two
  timestamps confirms the intermediary closed it well before the
  application detected anything.

## Fix
Make liveness an actively verified property, checked often enough to
beat every intermediary's idle timeout, on both ends:
- Implement WebSocket ping/pong (most server libraries expose this
  natively) at an interval meaningfully shorter than the shortest
  known idle timeout anywhere in the network path -- as a rule of
  thumb, well under half of it, to tolerate jitter and occasional
  missed beats without false-positiving.
- Track pong receipt against a deadline on the sending side: if no
  pong arrives within a bounded window after a ping, treat the
  connection as dead and actively close and clean it up server-side
  (freeing resources, notifying application logic) rather than waiting
  for a future send to fail.
- On the client, apply the same deadline-checking discipline for
  whichever heartbeat direction the protocol uses, and treat a missed-
  heartbeat deadline as equivalent to a `close` event -- triggering the
  same reconnect logic -- rather than only reacting to an explicit
  `close`/`error` event that may never fire.
- Configure any load balancer/proxy idle timeout in the path to be
  longer than the application's heartbeat interval where that's
  configurable, so the two are aligned by design rather than by
  coincidence.

## Pitfalls
- Implementing an application-level "heartbeat" as a regular JSON
  message rather than using the protocol's built-in ping/pong control
  frames means the heartbeat itself competes with real traffic for
  message-queue space and gets subject to the same backpressure/
  ordering as everything else, instead of being a lightweight
  out-of-band liveness check.
- Setting the heartbeat interval aggressively short "to be safe" on a
  large fleet multiplies baseline connection overhead and can itself
  become a meaningful load source at high connection counts -- tune it
  against actual measured intermediary timeouts rather than picking
  the smallest plausible number.
- Detecting a dead connection via missed heartbeat but not actually
  tearing down server-side resources (subscriptions, per-connection
  state, queue) for it leaves a "zombie" entry that still counts
  against connection limits and fan-out lists even though no client is
  there.

## Verify
Reproduce the idle-drop scenario (leave a connection idle behind the
production network path for longer than the shortest known
intermediary timeout) with the heartbeat in place, and confirm: the
connection either survives (pings/pongs keep it classified as active
by every intermediary) or, if genuinely dropped, both sides detect the
missed heartbeat within one heartbeat-interval-plus-deadline window and
transition to reconnect logic -- rather than only discovering the drop
whenever the next real application message happens to be attempted.
