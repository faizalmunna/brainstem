---
name: log-volume-cost-explosion
description: The logging/observability bill spikes sharply without a matching traffic increase -- log volume grew faster than the system it's monitoring.
triggers: ["logging bill spiked", "log volume exploded", "datadog bill too high", "too many logs", "log ingestion cost"]
permissions: ["READ"]
---

## Symptom

A logging/observability vendor bill (Datadog, Splunk, CloudWatch Logs,
Elastic) jumps significantly month over month, or a self-hosted log
store's disk/ingestion metrics climb steeply, with no corresponding
increase in request traffic or user count to explain it.

## Likely causes

- **Debug-level logging was left enabled in production** after being
  turned on temporarily to chase down an incident, and nobody turned it
  back off.
- **A new library or framework version started logging more verbosely by
  default** -- a dependency bump silently changed a default log level or
  added new log statements on a hot path.
- **A retry loop or error condition is logging on every attempt** -- a
  downstream dependency degrades, retries kick in every few hundred
  milliseconds, and each retry logs a full stack trace, multiplying log
  volume by the retry count during exactly the period everyone least wants
  a noisy log pipeline.
- **Per-request logging was added inside a loop** (logging once per item
  in a batch, once per row in a query result) instead of once per request
  with an aggregate count.
- **High-cardinality fields got added to structured logs** (full request
  bodies, full response payloads) inflating per-line size, so cost grows
  even at constant line count.

## Diagnose

1. Break down the volume increase by service/log level/logger name over
   the time window it appeared -- almost every logging backend supports
   this facet breakdown; find which specific logger or code path is
   actually responsible before touching anything.
2. Check whether the spike correlates with a deploy (a version bump, a
   config change) rather than a traffic event -- overlay deploy timestamps
   on the volume graph.
3. If the spike correlates with elevated error rates, check whether it's
   retry-amplified logging (the same logical failure logged N times for N
   retry attempts) rather than N independent failures.
4. Sample actual log lines from the noisiest logger and check line size,
   not just line count -- a cost spike with flat line count points at
   payload bloat, not a new log statement.

## Fix

Set log level per-environment explicitly in config (never rely on a
framework default), and make debug-level logging an intentional,
time-boxed toggle (a feature flag or env var with an expiry reminder) --
not a manual "we'll remember to turn it off." For retry-amplified
logging, log the failure once with a retry count and final outcome,
not once per attempt (log at `warn` per retry only if retries are rare
enough not to matter, at `debug` if they're routine). For loop-logging,
aggregate: log the batch outcome (count succeeded/failed) instead of a
line per item, and log per-item detail only for the failures. For payload
bloat, log identifiers and a truncated/redacted summary of the payload,
not the full body, and treat "log the whole payload for debugging" as
something to do surgically (a specific request ID, a short time window),
never as a standing log statement on a hot path.

## Pitfalls

Don't respond to a cost spike by dropping the log level globally to
`error` as a blanket fix -- that removes the `info`/`warn` signal that
would have caught the *next* incident earlier, trading a cost problem for
a debuggability problem. Also don't assume sampling logs (only keeping
some percentage) is a safe fix without checking what gets sampled out --
naive random sampling on errors specifically defeats the purpose, since
errors are exactly the rare, high-value lines you can't afford to lose
(see the tracing pack's sampling-bias skill for the same issue applied to
traces).

## Verify

After the fix, confirm the volume/cost graph returns to the pre-spike
baseline (adjusted for any real traffic growth in the meantime), and
deliberately trigger the original failure condition (or a synthetic
version of it) in a non-prod environment to confirm the fix didn't also
silence the signal needed to detect a recurrence.
