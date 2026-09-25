---
name: context-cancellation-not-propagated-http-client
description: Fix a canceled or timed-out incoming request whose downstream outbound HTTP call keeps running server-side instead of aborting immediately.
triggers: ["client disconnected but request keeps running", "context canceled not stopping http call", "downstream request doesn't abort on cancel", "request still processing after client closed connection", "context deadline exceeded but call continues"]
permissions: ["READ"]
---

## Symptom
A client disconnects, hits its own timeout, or the incoming request's context
is otherwise cancelled -- but the server keeps executing the handler, and in
particular an outbound HTTP call to a downstream service keeps running to
completion (visible as continued CPU/network activity, or the downstream
service's own logs showing the call finish long after the client gave up).
This wastes resources and, for non-idempotent downstream calls, can even
complete a side effect the original client no longer expects.

## Likely causes
1. **The outbound `http.Request` is built with `http.NewRequest` instead of
   `http.NewRequestWithContext`**, so it has no context attached at all --
   `net/http`'s transport only aborts a request when a context tied to it is
   cancelled, and a request built without one simply runs to completion.
2. **The handler's incoming request context is never passed down** -- a
   context is created fresh (`context.Background()` or a new
   `context.TODO()`) somewhere in a helper function or client wrapper instead
   of threading `r.Context()` (server) or the caller's `ctx` (any function)
   through, silently severing the cancellation chain at that boundary.
3. **A goroutine is spawned to make the downstream call and outlives the
   handler** -- the handler returns (or its context is cancelled) but the
   spawned goroutine captured a context that was never linked to cancellation,
   or captured no context at all, so it runs independently.
4. **The context is propagated correctly but the downstream HTTP client has
   its own longer timeout or retry logic that re-issues the call with a fresh,
   uncancelled context on each retry attempt.**

## Diagnose
- Grep every `http.NewRequest(` call (without `WithContext`) in the request
  path -- each one is a candidate for a silently disconnected cancellation
  chain.
- Trace the context variable from the handler entry point (`r.Context()`)
  through every function call down to the outbound request construction --
  look for any point where a new context is created instead of derived from
  the passed-in one (`context.WithTimeout(context.Background(), ...)` instead
  of `context.WithTimeout(ctx, ...)`).
- Reproduce directly: send a request to the endpoint, cancel it client-side
  (close the connection or use a client with a short timeout) partway
  through, and watch the downstream service's access logs -- if the
  downstream request still completes and logs a normal response after the
  client-side cancellation, propagation is broken somewhere in the chain.
- Add a `defer` at the very top of the handler that logs `ctx.Err()` a moment
  after return to confirm the incoming context itself is actually being
  cancelled by the framework on client disconnect (some middleware or
  frameworks need explicit configuration for this).

## Fix
Thread one context value from the inbound request all the way to the
outbound call, deriving (never replacing) it at every hop:
```go
func (s *Server) handle(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context() // don't discard this
    result, err := s.fetchDownstream(ctx, id)
    ...
}

func (s *Server) fetchDownstream(ctx context.Context, id string) (*Result, error) {
    req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
    if err != nil { return nil, err }
    resp, err := s.client.Do(req)
    ...
}
```
If a per-call timeout shorter than the caller's deadline is needed, derive it
with `context.WithTimeout(ctx, ...)` (not `context.Background()`), and always
`defer cancel()` immediately after creating it so resources release
regardless of which path returns. If a goroutine must outlive the immediate
call (e.g. fire-and-forget), that's a deliberate design choice -- give it its
own explicitly-scoped context with its own lifetime and cancellation policy,
rather than accidentally inheriting or accidentally losing the parent's.

## Pitfalls
- Wrapping a context in `context.WithTimeout` but forgetting `defer cancel()`
  leaks the internal timer goroutine until the timeout fires naturally, even
  though the call already finished.
- Passing `context.Background()` "just to get it compiling" during a refactor
  and forgetting to wire the real context back in is the single most common
  regression here -- it compiles fine and works in every test that doesn't
  specifically assert on cancellation.
- A downstream client's retry wrapper that catches `context.Canceled` and
  retries anyway defeats the entire propagation chain -- retry logic must
  check `ctx.Err()` and stop, not treat every error as retryable.

## Verify
Issue a request, cancel it from the client side after a fixed delay (e.g. via
`context.WithTimeout` on the test client or by closing the connection), and
confirm via the downstream service's logs or a traced span that the outbound
call's socket is closed/aborted within a small margin of the cancellation
time rather than running to its original completion time.
