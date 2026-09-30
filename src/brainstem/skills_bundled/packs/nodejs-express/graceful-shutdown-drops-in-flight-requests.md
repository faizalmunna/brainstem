---
name: graceful-shutdown-drops-in-flight-requests
description: Diagnose deploys or restarts that cut off in-flight Express requests with connection-reset errors instead of letting them finish first.
triggers: ["requests fail during deploy", "connection reset during rolling restart", "502 during deployment", "in-flight requests dropped on restart", "kubernetes pod terminated mid-request"]
permissions: ["READ"]
---

## Symptom
A deploy, rolling restart, or autoscaling scale-down produces a burst of
failed requests -- client-visible connection resets, `502`/`504`
responses from a load balancer, or abruptly terminated responses --
concentrated specifically in the window when old instances are being
replaced, even though the app is healthy and fast under normal operation
seconds before and after.

## Likely causes
1. **The process exits immediately on `SIGTERM`** with no shutdown
   handler at all -- the default behavior for many process managers/
   orchestrators is to send `SIGTERM`, wait a grace period, then
   `SIGKILL`; without a handler, the HTTP server (and any open sockets
   mid-response) gets torn down the instant the process exits, cutting
   off whatever was in flight.
2. **`server.close()` is called, but it only stops accepting new
   connections -- it doesn't forcibly end existing ones**, and the
   process's shutdown sequence doesn't actually wait for `close()`'s
   callback (which fires once all in-flight connections have finished)
   before exiting, or exits via `process.exit()` immediately after calling
   `close()` without awaiting anything.
3. **The load balancer/orchestrator keeps routing new requests to an
   instance for a brief window after it's already begun shutting down**
   -- a health check or readiness probe with too long a check interval,
   or no deregistration delay, so new requests arrive after `server.
  close()` has already stopped accepting connections and get connection
  errors instead of being routed elsewhere.
4. **Long-lived connections (keep-alive HTTP connections, WebSocket/SSE
   connections) are open when shutdown starts and are neither given time
   to finish nor explicitly notified to reconnect elsewhere**, so they're
   forcibly severed rather than drained.
5. **The shutdown grace period configured in the orchestrator
   (Kubernetes' `terminationGracePeriodSeconds`, PM2's kill timeout) is
   shorter than the app's actual shutdown handler needs** to finish
   in-flight work, so `SIGKILL` arrives and terminates the process
   mid-drain regardless of how well the handler is written.

## Diagnose
- Reproduce locally: send `SIGTERM` to the running process
  (`kill -TERM <pid>`) while a slow request is in flight (an endpoint
  with an artificial delay works well for this) and observe whether that
  request completes normally or gets cut off.
- Check whether a `SIGTERM` handler exists at all
  (`process.on('SIGTERM', ...)`) -- if none exists, this is the
  first and most direct cause to confirm; if one exists, read what it
  actually does versus what it's assumed to do (many "graceful shutdown"
  implementations call `server.close()` but don't wait for its callback,
  or call `process.exit()` unconditionally after a fixed timeout
  regardless of whether requests finished).
- During an actual deploy/restart in a staging environment, capture
  client-side error rates and timing precisely against the deployment
  event timestamp -- a spike that starts exactly at old-instance
  termination and lasts roughly the orchestrator's grace period strongly
  implicates shutdown handling over an application bug.
- Check the readiness/health-check configuration and deregistration
  timing relative to when the app actually stops accepting connections
  -- if the load balancer's check interval is longer than the time
  between shutdown signal and the app closing its listening socket, new
  requests can be routed in after the app has already started rejecting
  them.

## Fix
- Implement a `SIGTERM` handler that: stops the readiness probe from
  reporting healthy immediately (so the load balancer stops routing new
  traffic), calls `server.close()` to stop accepting new connections
  while letting existing ones finish, and only calls `process.exit()`
  inside `server.close()`'s callback (i.e., after it confirms all
  connections have ended) -- not immediately after calling `close()`.
- Set the orchestrator's grace period comfortably longer than the
  longest realistic in-flight request duration plus the time needed for
  the readiness-probe-driven deregistration to take effect elsewhere
  (Kubernetes' `terminationGracePeriodSeconds`, PM2's `kill_timeout`),
  and add a deliberate short delay before calling `server.close()` in
  the handler to give the load balancer time to stop routing new traffic
  first.
- For long-lived connections (WebSocket/SSE), on shutdown signal
  explicitly notify connected clients to reconnect (a close frame with a
  reconnect hint, or a graceful SSE stream end) rather than relying on
  the abrupt TCP-level disconnect they'd otherwise get.
- Add a hard timeout as a safety net inside the shutdown handler itself
  (e.g. force-exit after N seconds even if `server.close()`'s callback
  hasn't fired) so a single stuck connection can't prevent shutdown
  entirely and force a `SIGKILL` that skips any other cleanup (flushing
  logs, closing DB connections) the handler was also meant to do.

## Pitfalls
- Calling `process.exit()` synchronously right after `server.close()`
  without waiting for its callback defeats the entire purpose of calling
  `close()` -- `close()` is asynchronous specifically so in-flight
  connections can finish; exiting immediately after invoking it (rather
  than inside its callback, or after `await`ing a Promise-wrapped version
  of it) reintroduces the exact symptom the handler was meant to fix.
- Only handling `SIGTERM` and not `SIGINT` covers orchestrator-driven
  shutdowns but not a local `Ctrl+C` or some process managers' chosen
  signal -- handle both (and check what signal the specific deployment
  platform actually sends) rather than assuming `SIGTERM` alone covers
  every shutdown trigger.
- Making the readiness probe fail immediately on shutdown signal without
  also giving the load balancer time to notice and stop routing before
  `server.close()` takes effect can still produce a short window of
  failed connections -- sequence "stop reporting ready" before "stop
  accepting connections," with a deliberate gap between them, not
  simultaneously.

## Verify
During a real (or staging) rolling deploy, run a continuous load of
requests against the service (including some deliberately slow ones)
spanning the deploy window and confirm zero connection-reset/502 errors
attributable to the old instance's shutdown, with in-flight slow requests
completing successfully against the terminating instance before it
exits.
