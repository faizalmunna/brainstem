---
name: graceful-shutdown-drops-inflight-requests
description: Fix a Go HTTP server deployment that abruptly cuts off in-flight requests during a rolling deploy or pod termination instead of finishing them first.
triggers: ["requests dropped during deploy", "connection reset during rolling restart", "kubernetes pod termination drops requests", "graceful shutdown not working go server", "502 errors during deployment"]
permissions: ["READ"]
---

## Symptom
Every deployment or pod restart produces a small burst of client-visible
errors (connection reset, 502s from a load balancer, abruptly closed
connections) for requests that were in-flight at the exact moment the old
process was terminated -- even though the service otherwise runs fine, this
specific window during every rollout causes real user-facing failures.

## Likely causes
1. **The server calls `os.Exit` (directly, or via an unhandled `SIGTERM`
   default action) instead of `http.Server.Shutdown(ctx)`** -- the default
   behavior for `net/http.Server` on process termination is to simply stop,
   dropping any connection that's mid-request rather than letting it finish.
2. **`Shutdown` is called, but the process's SIGTERM handler doesn't actually
   wait for it to complete before the process exits** -- e.g. `Shutdown` is
   called in a goroutine without the main goroutine blocking on its return,
   or a fixed `time.Sleep` is used instead of actually waiting on `Shutdown`'s
   returned error/completion.
3. **The orchestrator (Kubernetes, a process manager) sends `SIGTERM`, waits
   a grace period, then sends `SIGKILL` -- but the grace period is shorter
   than the time in-flight requests actually need to finish**, so `Shutdown`
   is doing the right thing but gets killed before it completes; this is a
   configuration mismatch, not purely an application bug.
4. **The load balancer/service mesh keeps routing new requests to the pod
   for a brief window *after* it received SIGTERM and started shutting down**,
   because there's no delay between "stop accepting new traffic" and
   "the LB's routing table catches up" -- new requests still arrive during
   `Shutdown`'s drain window and get connection-refused if they arrive after
   the listener actually closes.

## Diagnose
- Check the process's signal handling code (or absence of it) -- grep for
  `signal.Notify` and confirm `SIGTERM` (not just `SIGINT`) is handled, and
  that the handler calls `server.Shutdown(ctx)` rather than allowing the
  default terminate-immediately behavior.
- Confirm the main goroutine actually blocks until `Shutdown` returns (or its
  context times out) before the process function returns -- a `go
  server.Shutdown(ctx)` call without a corresponding wait lets `main` exit
  immediately regardless of shutdown progress.
- Check the orchestrator's configured termination grace period (e.g.
  `terminationGracePeriodSeconds` in a Kubernetes pod spec) against the
  server's own shutdown timeout -- if the app's shutdown context timeout is
  longer than the orchestrator's grace period, the orchestrator's SIGKILL
  arrives first regardless of what the app does.
- During a real (or staged) deployment, watch client-side error logs/metrics
  for the exact timestamp window of errors and cross-reference against the
  pod's termination timestamp and readiness-probe-failing timestamp to see
  which of the above windows they fall into.

## Fix
Handle `SIGTERM` explicitly, call `Shutdown` with a bounded context, and
block until it completes (or times out) before letting the process exit:
```go
srv := &http.Server{Addr: ":8080", Handler: mux}
go srv.ListenAndServe()

sigCh := make(chan os.Signal, 1)
signal.Notify(sigCh, syscall.SIGTERM, syscall.SIGINT)
<-sigCh // block until a termination signal arrives

ctx, cancel := context.WithTimeout(context.Background(), 25*time.Second)
defer cancel()
if err := srv.Shutdown(ctx); err != nil {
    log.Printf("graceful shutdown did not complete: %v", err)
}
```
`Shutdown` stops accepting new connections immediately and waits for
active ones to finish (or the context to expire) before returning. Separately,
make the readiness probe fail (or add a short fixed delay before calling
`Shutdown`) as soon as SIGTERM is received, so the orchestrator/load balancer
has time to stop routing new traffic to this instance before its listener
actually closes -- this addresses the LB-lag cause, which `Shutdown` alone
doesn't solve. Finally, set the orchestrator's termination grace period
comfortably longer than the server's shutdown timeout plus the LB-drain
delay, not equal to it.

## Pitfalls
- Setting the shutdown context timeout very long "to be safe" without also
  extending the orchestrator's grace period just moves where the abrupt cut
  happens -- the two need to be tuned together, with the orchestrator's grace
  period the larger of the two.
- Forgetting that long-lived connections (WebSocket, SSE, long-polling) don't
  count as "finished" quickly under `Shutdown`'s definition -- these may need
  their own explicit close/drain logic (e.g. sending a close frame) rather
  than relying on `Shutdown` alone, which waits for the handler to return but
  won't forcibly interrupt a handler that's intentionally long-running.
- Skipping the pre-shutdown readiness-probe-failing delay because "Shutdown
  already stops new connections" ignores that the load balancer's view of
  pod health is asynchronous and lags behind the pod's own state -- the delay
  is what closes that gap, not `Shutdown` itself.

## Verify
Run a load test that keeps a steady stream of requests hitting the service,
trigger a real rolling restart/pod termination during the load test, and
confirm the client-observed error rate stays at zero (or matches an
explicitly accepted baseline) through the entire deployment window, not just
that the server logs "shutting down gracefully."
