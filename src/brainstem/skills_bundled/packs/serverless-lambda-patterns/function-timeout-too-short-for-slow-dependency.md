---
name: function-timeout-too-short-for-slow-dependency
description: A function's execution timeout is set too short for an occasionally-slow downstream call, causing intermittent failures that look unrelated to timeout configuration.
triggers: ["lambda times out intermittently", "function fails randomly under load", "task timed out after seconds lambda", "intermittent 504 serverless function"]
permissions: ["READ"]
---

## Symptom
A function fails intermittently -- maybe 1-2% of invocations -- with what
looks like a generic error: a truncated log with no stack trace, a
platform-generated "Task timed out after 3.00 seconds" line, or a caller
seeing a 504/502 with no application-level error message at all. The
failures don't correlate with any obvious bug in the code and are hard to
reproduce locally because the local environment or a direct test call to
the same dependency responds quickly.

## Likely causes
1. **The function's configured timeout was set based on typical-case
   latency of a downstream call (DB query, third-party API, another
   service) rather than its actual tail latency**, so the small fraction
   of calls that hit p99+ latency on that dependency exceed the timeout
   even though nothing is actually broken.
2. **The downstream dependency itself has an unbounded or very long
   client-side timeout/retry configuration**, so when it's slow, the
   function's own platform-level timeout fires first and kills the
   invocation mid-request, rather than the dependency's client failing
   fast with a catchable error.
3. **A cold start plus a slow dependency call together exceed the budget**
   -- the timeout was sized assuming a warm invocation, but cold-start
   initialization overhead (runtime bootstrap, module-level connection
   setup) eats into the same wall-clock budget, leaving less margin than
   assumed for the actual work.
4. **The timeout is inherited from a template/default value** (many IaC
   templates default to 3 or 6 seconds) and was never revisited when a
   new code path added a slower call, so the timeout reflects the
   function's original purpose, not its current one.
5. **Retries at a layer above the function (API Gateway, an orchestrator,
   a queue redrive) mask the real symptom** -- each retry also times out
   for the same reason, so what looks like "the request eventually failed"
   is actually N consecutive timeout failures, multiplying load on the
   already-slow dependency.

## Diagnose
- Pull the function's own execution duration metric (e.g., CloudWatch
  `Duration`) and look at p50 vs. p99 vs. max, not just the average --
  if p99 is close to or exceeds the configured timeout, that's the
  smoking gun, distinct from a genuine error rate.
- Cross-reference invocation timestamps of the failures against the
  downstream dependency's own latency metrics/logs (RDS `Latency`,
  an API's response time histogram) for the same time window --
  a spike in the dependency's tail latency lining up with the function's
  timeouts confirms causation.
- Check whether failures cluster after deploys, scaling events, or
  specific times of day (e.g., a downstream DB doing maintenance or
  autovacuum) -- a temporal pattern points at the dependency, not the
  function's own code.
- Read the actual platform log line for a failed invocation, not just the
  application log -- a hard timeout kill often produces a distinct
  platform-generated message ("Task timed out") that a generic
  try/catch around application code will never see or log itself.
- Check the downstream client library's own configured timeout value
  against the function's total timeout -- if the client's timeout is
  longer than (or equal to) the function's timeout, the function will
  always die first with no clean error surfaced from the client.

## Fix
Set the function's timeout based on the downstream dependency's measured
p99/p999 latency plus explicit margin for cold start and platform
overhead, not the median case -- treat it as a capacity/SLA decision, not
an arbitrary default. Configure the downstream client's own timeout to be
meaningfully shorter than the function's total timeout (e.g., function
timeout 10s, HTTP client timeout 6s) so a slow call fails fast with a
catchable, loggable exception instead of being killed abruptly by the
platform with no application-level context. For genuinely slow but
non-critical-path work, move it out of the synchronous request path
entirely (queue it, or use an async invocation pattern) rather than
inflating the timeout to accommodate it. Add explicit timeout/retry
logging around the specific downstream call so a future incident shows
"call to X took 9.8s and was aborted" instead of an opaque platform kill.

## Pitfalls
Simply raising the function's timeout to some large number (e.g., 15
minutes) as a blanket fix hides the real tail-latency problem in the
dependency and can turn a fast-failing request into one that ties up
concurrency slots for much longer under load, worsening a concurrency
throttling situation elsewhere in the same account/app. Also, increasing
only the function's timeout without also increasing (or explicitly
capping) the downstream client's timeout doesn't help -- the client may
still return an ambiguous error or hang in a way the extra function time
budget doesn't actually fix.

## Verify
Inject artificial latency into the downstream dependency in a test
environment (a delay proxy, a feature flag, or a mock that sleeps near the
old timeout threshold) and confirm the function now either completes
successfully within the new timeout margin or fails with a clear,
attributable "downstream call exceeded client timeout" error rather than
a bare platform timeout kill.
