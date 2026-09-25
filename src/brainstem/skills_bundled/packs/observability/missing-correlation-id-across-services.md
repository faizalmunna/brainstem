---
name: missing-correlation-id-across-services
description: A single user request or job can't be traced across service/log boundaries because no consistent correlation ID travels with it end to end.
triggers: ["can't correlate logs across services", "no request id", "can't trace a request through microservices", "correlation id missing"]
permissions: ["READ"]
---

## Symptom

Debugging an issue reported for one user's request requires manually
cross-referencing timestamps and guesswork across several services' logs,
because there's no single ID present in every log line touched by that
request. Support/on-call ends up saying "logs from around that time" as a
substitute for a precise, reliable lookup.

## Likely causes

- **No correlation ID is generated at all** at the system's entry point
  (API gateway, load balancer, edge service) -- each service that wants
  one generates its own independently, producing a different ID per hop.
- **The ID is generated but not propagated** past the first service's
  outbound calls -- it's not attached as a header on downstream HTTP
  calls, not attached to a queue message's metadata, not passed into a
  background job's arguments.
- **The ID exists in traces (via the tracing system's trace ID) but isn't
  also surfaced into logs** -- so a request can be found in the tracing UI
  but the corresponding log lines can't be found by the same ID, because
  the log statements never included it as a field.
- **A different, incompatible ID is generated per protocol boundary** --
  the HTTP layer generates one request ID, a message queue library
  generates a completely separate message ID, and nothing links the two
  together as "the same logical operation."

## Diagnose

1. Pick one real request and manually attempt the correlation across every
   service it touches -- note exactly which hop is where the ID either
   changes, disappears, or was never present.
2. Check the entry-point service (gateway/edge/first API) for whether it
   generates an ID on every inbound request, and whether that generation
   happens before or after routing to the eventual handler (a common gap:
   generated in middleware that only wraps some routes).
3. For each downstream call type (HTTP, queue, background job, scheduled
   task) check separately whether the ID is explicitly forwarded --
   propagation across HTTP calls doesn't imply propagation into a queue
   message, they're separate wiring.
4. Check whether the trace ID from the tracing system (if one exists,
   see `distributed-trace-missing-context`) could serve as the same
   correlation ID for logs, avoiding maintaining two separate IDs.

## Fix

Generate a correlation ID once, at the system's true entry point, for
every inbound request (and independently for every scheduled/cron-
triggered job, since those have no inbound request to attach to). Prefer
reusing the distributed tracing system's trace ID as the correlation ID
rather than inventing a second, parallel ID -- one ID that appears in both
logs and traces is strictly easier to work with than two IDs that have to
be cross-referenced. Explicitly propagate it on every outbound call type
the service makes: HTTP headers, queue message metadata/attributes,
background job arguments -- each protocol needs its own explicit wiring,
typically via middleware/interceptor so individual call sites don't have
to remember. Inject it into the logging context (most structured logging
libraries support a "current context fields" mechanism) so every log
statement for the duration of handling that request includes it
automatically, rather than requiring every log call to pass it manually.

## Pitfalls

Don't generate a *new* correlation ID at every service hop "just to be
safe" -- that reproduces the exact problem (a different ID per hop) under
a different name. Also don't forget the entry points that aren't HTTP
requests -- scheduled jobs, queue consumers acting as their own entry
point, admin scripts -- these need their own ID generated at their own
start, since there's no upstream request to inherit one from.

## Verify

Trigger one request through the full path and confirm a single ID
(ideally, the trace ID) appears in every service's log output for that
request, filterable with one query across the whole log pipeline. Repeat
for at least one non-HTTP entry point (a queue-triggered job) to confirm
propagation isn't HTTP-only.
