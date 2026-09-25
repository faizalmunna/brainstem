---
name: lambda-concurrency-throttling-silent
description: Lambda invocations silently fail or get dropped under load because the account or function concurrency limit is reached and callers see no clear error.
triggers: ["lambda throttling silently", "lambda invocations disappearing", "lambda reserved concurrency limit", "429 too many requests lambda", "lambda events dropped no error"]
permissions: ["READ"]
---

## Symptom
Under moderate-to-heavy load, some fraction of Lambda invocations simply
never happen or never produce a visible result -- API Gateway callers get
intermittent 500/502s, an SQS-triggered function stops making progress on
its queue, or an async invocation (S3 event, EventBridge) appears to
vanish -- with nothing obviously wrong in the function's own logs, because
the throttled invocations never reached the function's code at all.

## Likely causes
1. **Account-level (or function-level reserved) concurrency limit
   reached** -- Lambda enforces a hard cap on simultaneously executing
   instances of a function (or the whole account, default 1000 unless
   raised), and once at the cap, additional invocation attempts are
   throttled (`TooManyRequestsException` / HTTP 429) rather than queued
   indefinitely.
2. **A synchronous invocation path (API Gateway, ALB) surfaces throttling
   as a generic 5xx** because the caller's SDK or the API Gateway
   integration doesn't distinguish "Lambda throttled me" from "Lambda
   errored," so the throttle is invisible unless someone specifically
   checks the `Throttles` CloudWatch metric.
3. **An asynchronous invocation path (S3, SNS, EventBridge) retries
   throttled events automatically and then sends them to a
   dead-letter queue or on-failure destination if retries are exhausted**
   -- if no DLQ/destination is configured, the event is silently dropped
   after retries, with no trace it ever existed.
4. **One noisy function's reserved concurrency (or lack of a reserved
   limit) starves other functions in the same account** by consuming the
   shared account-level concurrency pool, so an unrelated function starts
   throttling because of a neighbor's traffic spike, not its own.
5. **SQS-triggered Lambda's concurrency is capped below the queue's
   incoming rate**, so messages back up in the queue (visible as growing
   `ApproximateNumberOfMessagesVisible`) while individual Lambda
   invocations look fine in isolation -- the bottleneck is the trigger's
   effective concurrency, not any single invocation.

## Diagnose
- Check the `Throttles` CloudWatch metric for the specific function (and
  `ConcurrentExecutions` against `UnreservedConcurrentExecutions` at the
  account level) for the exact time window of the reported failures --
  nonzero `Throttles` confirms this before looking at anything else.
- For synchronous invocations, check API Gateway's own `5xxError` /
  `IntegrationLatency` metrics and, if using ALB, the target group's error
  metrics -- a 429 from Lambda often surfaces upstream as a plain 500 with
  no body detail unless you check Lambda's own metric directly.
- For async invocations, check whether a dead-letter queue or on-failure
  destination is configured (`get-function-event-invoke-config`) -- if
  none is set, confirm the absence of dropped-event records is expected
  behavior, not a separate bug.
- For SQS-triggered functions, compare the queue's
  `ApproximateNumberOfMessagesVisible` trend against the function's
  `ConcurrentExecutions` -- a growing backlog with flat concurrency
  indicates the trigger's concurrency (capped by reserved concurrency or
  the account limit) is the bottleneck.
- Check whether the function has **reserved concurrency** set at all
  (`function-level Concurrency` in the console/CLI) -- an unset reserved
  concurrency means it draws from the shared account pool, which a
  neighboring function can exhaust.

## Fix
Set reserved concurrency deliberately on functions that must not starve
or be starved by others, sized to real expected peak load with margin,
rather than leaving every function drawing from the shared pool. Request
an account-level concurrency limit increase via Service Quotas if
legitimate aggregate traffic across functions regularly approaches the
default ceiling. For asynchronous invocation sources, configure a
dead-letter queue or on-failure destination explicitly so throttled/failed
events are captured and replayable instead of silently disappearing. For
SQS-triggered functions, size the queue's consumer concurrency
(`ReservedConcurrentExecutions` on the function, and batch size) to match
expected throughput, and consider a redrive policy on the source queue so
messages that fail repeatedly land in a DLQ rather than looping. For
synchronous callers (API Gateway), add explicit handling/backoff for 429s
in the client rather than treating any 5xx the same way, so throttling is
distinguishable from real errors in caller-side observability.

## Pitfalls
Simply raising reserved concurrency on every function "to be safe" doesn't
fix the underlying account-level ceiling -- reserved concurrency
partitions the existing pool, it doesn't add capacity, so over-reserving
across many functions can itself cause unrelated functions to throttle
against a now-smaller unreserved pool. Also, adding a DLQ without ever
monitoring or alerting on it just moves the silent failure from
"invocation vanished" to "invocation sits unnoticed in a DLQ forever" --
a DLQ needs an alarm on `ApproximateNumberOfMessagesVisible` to be useful.

## Verify
Re-run the load pattern that originally caused drops while watching the
function's `Throttles` metric live -- it should read zero (or an
explicitly accepted, alarmed-on nonzero if intentionally capped). For the
async path, confirm a deliberately-forced throttle (e.g., temporarily
setting reserved concurrency to 0) results in events appearing in the
configured DLQ/destination rather than disappearing, then restore the
setting.
