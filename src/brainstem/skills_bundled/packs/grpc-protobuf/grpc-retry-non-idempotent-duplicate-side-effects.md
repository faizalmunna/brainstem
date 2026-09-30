---
name: grpc-retry-non-idempotent-duplicate-side-effects
description: Automatic gRPC retries on a transient failure cause a non-idempotent RPC's side effect to execute more than once for a single logical request.
triggers: ["grpc retry caused duplicate", "grpc automatic retry double write", "service config retry policy duplicate side effect", "grpc unavailable retry twice", "retried rpc created two records"]
permissions: ["READ"]
---

## Symptom
An RPC that performs a side effect (creates a record, sends a
notification, charges an account, appends to a log) occasionally executes
that side effect twice for what the caller believes is a single logical
request. Investigation shows the client actually sent the request twice
at the transport level -- not due to application bug, but because gRPC's
built-in retry mechanism (service-config retry policy, or a
hedging/retry interceptor) resent the call after a transient failure that
turned out to have already reached and been processed by the server.

## Likely causes
1. **A retry policy is configured for a method that isn't actually
   idempotent**, treating it the same as a safe-to-retry read -- gRPC's
   service-config retry policy is applied per-method by name pattern, and
   if it's set broadly (e.g. for an entire service) without excluding
   mutating methods, non-idempotent RPCs get retried right alongside
   idempotent ones.
2. **The failure that triggered the retry occurred *after* the server
   had already fully processed the request** -- e.g. the server committed
   the write and then the response was lost in transit (network blip,
   client-side timeout racing the response, load balancer connection
   reset) -- from the client's perspective this is indistinguishable from
   "the request never arrived," so a naive retry-on-any-transient-error
   policy resends a request that already succeeded.
3. **Retries are layered at multiple levels simultaneously without
   coordination** -- e.g. the gRPC client library's own retry policy plus
   an application-level retry wrapper plus a client-side circuit
   breaker/resilience library all independently decide to retry the same
   logical call, multiplying the effective retry count beyond what any
   single layer's configuration suggests.
4. **Hedging (sending a duplicate request proactively before the first
   one fails, to reduce tail latency) is enabled for a method where a
   "duplicate" isn't safe** -- unlike retry-on-failure, hedging
   intentionally sends more than one copy of the request concurrently,
   which is only safe for idempotent/read-only methods.

## Diagnose
- Check the service config (or client channel options) for retry policy
  definitions and confirm exactly which method names they apply to --
  look for a wildcard or service-wide policy that inadvertently includes
  mutating RPCs alongside reads.
- Reproduce by simulating a response-lost-after-commit scenario: inject a
  delay or drop on the response path only (not the request path) after
  the server has processed the write, and confirm whether the client's
  configured retry policy resends and causes a second write.
- Search the client codebase for retry logic at more than one layer --
  grep for retry-related interceptor registration, resilience library
  usage (e.g. Polly, resilience4j, custom backoff wrappers) *and*
  gRPC service-config retry settings in the same call path, since any
  combination compounds.
- Check server-side logs/metrics for the actual number of times the
  handler for the affected method was invoked per logical operation
  during an incident, correlated by any client-supplied correlation ID,
  to confirm duplicate invocation versus a downstream duplicate caused by
  something else (e.g. a message queue redelivery).

## Fix
- Scope retry (and hedging) policies explicitly to genuinely idempotent
  methods only -- naturally idempotent reads/lookups, or writes that are
  idempotent by design (an upsert keyed on a client-supplied ID) -- and
  explicitly exclude create/charge/send-style methods from any
  service-wide or wildcard retry configuration.
- For mutating RPCs that must tolerate retries (because the client
  legitimately can't otherwise distinguish a lost response from a lost
  request), make the operation idempotent at the application level: have
  the client attach an idempotency key/request ID generated once per
  logical operation, and have the server deduplicate on that key before
  executing the side effect, returning the original result on a repeat.
- Consolidate retry responsibility to a single layer in the call stack
  (prefer the gRPC service-config policy over ad hoc application retry
  wrappers, or vice versa, but not both) so total retry behavior is
  visible and configurable in one place instead of the product of several
  independently-tuned layers.
- Where hedging is used, restrict it to read-only methods and confirm the
  service-config's `hedgingPolicy` isn't accidentally applied to any
  method that mutates state.

## Pitfalls
- Marking a method idempotent based on its *name* (e.g. anything called
  `Update...`) rather than its actual behavior -- an "update" that
  appends to a list or increments a counter is not idempotent even though
  the name suggests a safe overwrite.
- Adding an idempotency key to the request but checking-and-inserting it
  as two non-atomic steps in the handler -- under concurrent retries this
  reintroduces the exact race the key was meant to close; the
  check-and-record must be a single atomic operation (a unique
  constraint, a conditional write).
- Disabling all retries entirely as an overcorrection -- this trades
  duplicate side effects for reduced resilience against genuinely
  transient failures on the RPCs that were safe to retry in the first
  place; scope the fix to the specific non-idempotent methods, don't
  remove retry policy wholesale.

## Verify
For the affected method, simulate a response-lost-after-server-commit
failure (drop the response after the handler completes, before it
reaches the client) and confirm the client's retry fires a second
request, then confirm the *side effect itself* happens exactly once
(via the idempotency key dedup, or by design) while the client still
receives a correct successful response on the retried call.
