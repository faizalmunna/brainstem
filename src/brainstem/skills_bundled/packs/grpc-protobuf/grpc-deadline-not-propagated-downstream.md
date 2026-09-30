---
name: grpc-deadline-not-propagated-downstream
description: A client gives up on a gRPC call after its deadline expires, but the downstream service keeps executing the request as if nothing happened.
triggers: ["deadline exceeded but downstream still running", "grpc context deadline not propagated", "downstream call keeps running after client timeout", "wasted work after client cancels grpc", "deadline doesn't cascade to child call"]
permissions: ["READ"]
---

## Symptom
A client sets a deadline (say 2 seconds) on a gRPC call. The call returns
`DEADLINE_EXCEEDED` to the client on time, but logs/traces show the
service that received the call -- and any services *it* in turn calls --
kept processing well past the 2-second mark, eventually completing (or
timing out on its own, much later) work that nobody is waiting for
anymore. This shows up as wasted CPU/DB load under timeout pressure, and
sometimes as a completed side effect (e.g. a write) for a request the
client believes failed.

## Likely causes
1. **The server handler never checks the incoming context for
   cancellation/deadline** before or during expensive work -- it received
   the deadline metadata correctly but the business logic just doesn't
   look at `ctx.Err()` / `context.isCancelled()` at any point, so nothing
   short-circuits.
2. **The deadline isn't forwarded to the downstream (child) RPC call** --
   the handler makes its outbound call with a fresh, unbounded context (or
   a newly created one with its own separate timeout) instead of the
   incoming request's context, so the parent's deadline has no effect on
   the child call at all.
3. **A goroutine/thread/async task is spawned to do the actual work and
   detached from the request context** (fire-and-forget pattern, or work
   handed to a background pool) -- cancelling the parent context has no
   way to reach code that no longer holds a reference to it.
4. **An intermediate hop (a proxy, gateway, or middleware layer) drops
   the deadline metadata entirely**, e.g. a custom interceptor that builds
   outgoing calls from scratch rather than deriving them from the
   inbound context, or a language binding where the deadline must be
   explicitly re-derived (not automatic) when hopping between RPC
   frameworks.

## Diagnose
- Trace a single slow request end-to-end (distributed tracing, or
  correlated request IDs in logs) and check the timestamp at which each
  hop's handler *started* versus when the top-level client gave up --
  if downstream work continues well past the client's deadline, the
  propagation chain is broken somewhere in that path.
- In the suspect handler, log `context.Err()` (Go) or check
  `Context.CancellationToken.IsCancellationRequested` (.NET) /
  `context.is_active()` (Python grpc) at the start of any expensive loop
  or before any downstream call, and confirm it actually flips to
  cancelled at the expected time in a controlled test.
- Check every outbound call site in the handler: is the context/method
  used to build the downstream request the *same* context object received
  from the inbound call (or a child derived from it via
  `context.WithTimeout(parentCtx, ...)`), or is it a bare
  `context.Background()` / newly constructed deadline?
- For spawned background work, check whether the spawned task captures
  the request context by reference or copies only the request data --
  if only data was copied, cancellation can never reach it.

## Fix
- Derive every downstream call's context from the inbound request's
  context, optionally narrowing (never widening) the deadline for a
  sub-call budget: `childCtx, cancel := context.WithTimeout(parentCtx,
  subBudget)` -- this way cancelling or timing out the parent
  automatically cancels every derived child.
- Make handlers actually observe cancellation during long-running work:
  check `ctx.Err()` between chunks of a loop, wire cancellation into any
  blocking I/O (DB driver, HTTP client) that accepts a context, and abort
  early rather than running to completion regardless.
- If work must legitimately outlive the request (e.g. an intentional
  async job), don't rely on the request context for it at all --
  explicitly hand off to a job system with its own lifecycle, and return
  to the client immediately rather than blocking on it under a deadline
  that isn't meant to bound it.
- Where the RPC framework doesn't propagate deadlines across a language
  or protocol boundary automatically (e.g. gRPC-Java through a JNI
  bridge, or a gRPC-to-HTTP gateway), explicitly read the incoming
  deadline (`grpc-timeout` metadata) and re-apply it to the outbound call
  rather than assuming it carries over.

## Pitfalls
- Propagating the parent's *full remaining* deadline to a downstream call
  without subtracting the time already spent, plus buffer -- this races
  the downstream call against the parent deadline expiring during network
  transit and burns the entire budget on a call that then still gets
  cancelled with no time left for a fallback or clean error path.
  Budget child calls with headroom, not the full inherited timeout.
- Checking cancellation only at the very start of the handler -- catches
  a client that's already gone before work begins, but not one that
  cancels midway through a long operation.
- Swallowing the cancellation error from a downstream call and retrying
  or falling back as if it were a normal failure -- a cancelled context
  means "nobody wants this result," not "try again."

## Verify
Set a client deadline shorter than the actual end-to-end processing time,
issue the call, and confirm via tracing/logs that every hop in the chain
(including the deepest downstream call) stops observably (aborted
DB query, cancelled HTTP request, handler returning early) at
approximately the deadline, not continuing to natural completion.
