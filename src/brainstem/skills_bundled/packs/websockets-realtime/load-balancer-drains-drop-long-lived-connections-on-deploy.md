---
name: load-balancer-drains-drop-long-lived-connections-on-deploy
description: Load balancer connection draining during a rolling deploy abruptly terminates long-lived WebSocket connections instead of handing them off gracefully.
triggers: ["clients disconnected during deploy", "websockets drop every time we deploy", "connection draining kills sockets", "rolling deploy causes mass disconnects", "deploy triggers reconnect spike"]
permissions: ["READ"]
---

## Symptom
Every rolling deploy or autoscaling scale-down event produces a
visible spike in WebSocket disconnects and client-side reconnect
attempts, timed almost exactly to when old instances are terminated --
even though the deploy pipeline reports a clean, healthy rollout with
no errors. Users notice brief "reconnecting..." states or dropped
real-time updates specifically during deploy windows, and the
disconnect count roughly matches the number of connections the
outgoing instances were holding, not a random subset.

## Likely causes
1. **The load balancer's default connection draining is designed for
   short-lived HTTP requests**, giving a fixed drain timeout under the
   (correct, for HTTP) assumption that in-flight requests finish in
   seconds -- but a WebSocket connection can legitimately stay open
   for hours, so when the drain timeout expires the LB force-closes
   every WebSocket still attached to that instance regardless of
   whether it was mid-conversation.
2. **The deploy process sends `SIGTERM` and then `SIGKILL` on a short
   grace period** tuned for stateless request handlers, without the
   application ever telling *clients* it's shutting down -- so
   connections vanish with a raw TCP reset/close from the client's
   perspective instead of a clean, informative close.
3. **No coordination between the orchestrator's shutdown sequence and
   the WebSocket server's own connection lifecycle** -- the instance
   is removed from the load balancer's healthy pool (stopping *new*
   connections) but existing connections aren't proactively
   redirected or closed with a reason, so they simply sit until the
   drain timeout or process kill cuts them off with no warning
   the client's reconnect logic can react to ahead of time.
4. **Sticky sessions mean a client's reconnect target is still the
   dying instance for some window** -- if session affinity is cached
   (client-side, DNS-level, or LB-level) longer than the drain window,
   the client's very first reconnect attempt can be routed right back
   to the instance that's in the process of shutting down.

## Diagnose
- Check the load balancer/ingress configuration for its connection
  draining or "deregistration delay" setting and compare it against
  the application's actual typical WebSocket connection duration --
  a drain timeout of 30-60 seconds (a common HTTP-oriented default)
  against connections that routinely live for hours confirms a
  mismatch.
- Correlate deploy timestamps (from the deploy pipeline's own logs)
  with the WebSocket close-code distribution during that window -- a
  spike specifically in abnormal closure codes (1006, or raw TCP
  resets with no close frame at all) rather than clean 1000/1001
  closes indicates the connection was cut rather than closed
  gracefully.
- Check whether the application has a `SIGTERM` handler that does
  anything beyond stopping new connections -- specifically, whether it
  sends a WebSocket close frame with an application-specific code
  ("server restarting, reconnect") to each currently-open connection
  before the process actually exits.
- Check the deploy/orchestrator's grace period (e.g. Kubernetes
  `terminationGracePeriodSeconds`) against how long it actually takes
  to notify and close all connections on a fully-loaded instance --
  if the grace period is shorter than that, the process gets killed
  mid-notification.
- Inspect client-side reconnect target resolution immediately after a
  disconnect during a deploy window -- confirm whether it re-resolves
  DNS/goes back through the load balancer fresh, or reuses a cached
  target that could still point at the terminating instance.

## Fix
Make shutdown a coordinated, multi-step sequence rather than a single
timeout-driven cutoff:
- On `SIGTERM`, first deregister the instance from the load balancer's
  healthy pool (stop new connections) but keep the process alive and
  serving existing connections; then actively iterate every open
  WebSocket connection and send a close frame with a specific code/
  reason the client can distinguish from an error (e.g. a custom code
  meaning "planned restart, reconnect now"), rather than waiting
  passively for the drain timeout.
- Set the orchestrator's termination grace period comfortably longer
  than the time it takes to notify and close the instance's full
  connection load, so the process isn't `SIGKILL`ed mid-drain; make
  this proportional to typical connections-per-instance if that
  varies significantly across deploys.
- Configure the load balancer's own draining/deregistration delay to
  match or exceed the same window, and prefer a target group/ingress
  feature that supports a longer, WebSocket-aware draining period over
  accepting an HTTP-tuned default.
- Have clients that receive the "planned restart" close code reconnect
  immediately (no backoff needed -- this isn't an outage, it's an
  expected, individually-timed handoff) but still apply jitter across
  the fleet of clients being drained together, so a large instance's
  connections don't all reconnect in the same instant and recreate the
  herd problem this pack's reconnection-storm skill describes.

## Pitfalls
- Sending the close frame to all connections on an instance
  simultaneously the moment `SIGTERM` is received just moves the
  thundering-herd problem from "load balancer timeout" to "graceful
  shutdown," rather than eliminating it -- stagger the notify-and-close
  loop across the instance's own connections over some seconds.
- Relying solely on the load balancer's deregistration delay without
  an application-level close-and-notify step still leaves clients
  discovering the disconnect via a timeout/dead-socket detection
  instead of an immediate, actionable signal, reintroducing the
  silent-disconnect problem this pack's heartbeat skill addresses.
- Extending the grace period without also bounding how many
  connections one instance is allowed to hold can make deploys
  arbitrarily slow as fleet size and connections-per-instance grow --
  pair a longer grace period with a per-instance connection cap so
  drain time stays predictable.

## Verify
Run a rolling deploy against a fully-loaded staging instance and
confirm: WebSocket close-code metrics during the deploy show the
custom "planned restart" code rather than 1006/abnormal closures,
client-side logs show immediate (not timeout-triggered) reconnects
staggered over the notify window rather than all at once, and no
connection is still open on the old instance by the time the
orchestrator actually terminates the process (checked via the
instance's active-connection count reaching zero before exit).
