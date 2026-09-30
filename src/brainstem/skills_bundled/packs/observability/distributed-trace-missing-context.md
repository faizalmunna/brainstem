---
name: distributed-trace-missing-context
description: A request's trace shows disconnected spans (or a single-service span) instead of one continuous trace across services -- context propagation is broken somewhere.
triggers: ["trace is broken", "spans not connected", "can't see the full request trace", "trace context lost", "distributed trace incomplete"]
permissions: ["READ"]
---

## Symptom

Opening a trace for a slow or failing request in the tracing UI (Jaeger,
Tempo, Datadog APM, Honeycomb) shows either a single orphaned span with no
children, or two unconnected trace trees that clearly belong to the same
user request but never link up. The trace ends at a service boundary
instead of continuing into the downstream call.

## Likely causes

- **The propagation headers (`traceparent`/`tracestate`, or a vendor
  header like `x-datadog-trace-id`) are dropped** at a hop that doesn't
  forward arbitrary headers -- a proxy, API gateway, or load balancer with
  an explicit allow-list of forwarded headers that predates tracing being
  added.
- **Async boundaries lose context** -- a message dropped onto a queue
  (Kafka, SQS, RabbitMQ) or a background job enqueued from a request
  handler doesn't carry the trace context in the message metadata, so the
  consumer starts a brand-new, disconnected trace.
- **Two different tracing SDKs/propagators are mixed** across services --
  one team's service emits W3C Trace Context, another's emits B3 headers,
  and nothing in between translates -- so each side parses the other's
  header as absent.
- **The span is force-flushed/ended before the async work it wraps
  actually completes** (fire-and-forget calls, unawaited promises), so the
  child span either never reports or reports against the wrong parent.
- **Sampling decisions disagree between services** -- head-based sampling
  made independently per service means one service samples a trace in
  while the caller sampled it out, so the child span exists with no
  visible parent.

## Diagnose

1. Pick one broken trace and inspect the raw outgoing request/message from
   the upstream service (curl reproduction, or a packet/log capture) --
   confirm whether the propagation header is actually present on the wire,
   not just assumed present because the SDK is installed.
2. If it's present on the wire but the trace still looks disconnected,
   compare the header format on both sides (W3C `traceparent: 00-<trace
   id>-<span id>-<flags>` vs B3's `X-B3-TraceId`/`X-B3-SpanId`) --
   a format mismatch means one side genuinely can't parse the other's ID.
3. For queue/async breaks: check whether the message envelope/job payload
   has a trace-context field at all, versus the context only existing in
   the enqueueing thread's in-memory span context that never gets
   serialized.
4. Check each service's sampling configuration for whether it's
   head-based (decided once, at the root, and expected to propagate) or
   independently decided per service -- the latter is the actual bug in a
   "sometimes connects, sometimes doesn't" pattern.

## Fix

Standardize on **one propagation format** across every service (W3C Trace
Context is now the interoperable default most vendors support natively;
pick it unless there's a hard reason not to), and treat header forwarding
through proxies/gateways as an explicit allow-list entry, not an
afterthought discovered by a broken trace. For async boundaries, the trace
context must be explicitly serialized into the message/job payload at
enqueue time and explicitly extracted to start a *linked* (not orphaned)
span at dequeue time -- most tracing SDKs have a documented pattern for
this (e.g., OpenTelemetry's `Propagator.inject`/`extract` called manually
around the queue client). For sampling, make the decision once at the
trace root and propagate the *decision* (not just the trace ID) downstream
so every service honors the same in/out choice for that trace.

## Pitfalls

Don't "fix" this by cranking sampling to 100% everywhere to make the
symptom go away -- it hides propagation bugs instead of fixing them, and
creates a new, worse problem (trace volume/cost explosion, see
`metric-cardinality-explosion` and the logging-cost skill in this pack for
the same failure mode applied to traces). Also don't assume a vendor's
auto-instrumentation handles every async framework's queue client
automatically -- many auto-instrumentation libraries cover HTTP and a
short list of popular queue clients, not every one, so a custom or less
common queue client often needs the manual inject/extract wiring above.

## Verify

Send one request through the full multi-service path with a known,
searchable identifier (a header or query param unlikely to collide), then
confirm in the tracing UI that a single trace ID contains every hop as
child spans of one root, including anything that crossed an async
boundary. Repeat once more after an hour to confirm it wasn't a
one-off caused by an unusually low-latency race.
