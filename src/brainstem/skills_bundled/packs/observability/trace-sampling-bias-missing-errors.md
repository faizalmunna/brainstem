---
name: trace-sampling-bias-missing-errors
description: Tracing is enabled and traces exist, but the specific slow/error traces needed to diagnose an issue aren't in the sample -- sampling is biased toward the boring, common case.
triggers: ["can't find the error trace", "sampling missed the slow request", "trace sampling bias", "no traces for the errors"]
permissions: ["READ"]
---

## Symptom

While debugging a specific slow or failing request, the tracing UI shows
plenty of traces from around the right time, but none of them are *the*
request in question, or none show the error/high latency at all --
despite tracing being enabled and apparently working for "normal"
requests.

## Likely causes

- **Uniform random head-based sampling** (e.g., "sample 1% of all
  requests," decided before the request's outcome is known) applied
  without any bias toward interesting outcomes -- at low traffic-relative
  rates, a rare error or an unusual slow request has a real chance of
  simply never being selected.
- **The sampling decision is made too early** (at the very start of the
  request, before latency or error status is known) with no mechanism to
  retroactively "keep" a trace that turned out to be interesting.
- **Tail-based sampling isn't in use** -- tail-based sampling (buffering
  spans and deciding whether to keep the whole trace only after it
  completes, based on outcome) is specifically designed to solve this,
  but requires more infrastructure (a collector that buffers) than simple
  head-based sampling, so many setups default to head-based and never
  revisit it.
- **A sampling rate that was reasonable at lower traffic wasn't revisited
  as traffic grew** -- the same 1% that used to capture a reasonable
  absolute number of error traces now captures too few in absolute terms
  even though the percentage didn't change.

## Diagnose

1. Confirm the sampling strategy actually in use (check the tracing SDK/
   collector config) -- head-based with a fixed percentage, versus
   tail-based, versus rate-limiting-based.
2. If head-based, calculate the expected number of sampled traces for the
   specific error/slow condition given its actual occurrence rate and the
   sampling percentage -- a low product number (e.g., a 0.1% error rate at
   1% sampling over a short window) explains "traces exist but not for
   this" without any misconfiguration, just math.
3. Check whether the tracing vendor/collector supports tail-based or
   error-biased sampling (many do, as an add-on to base sampling) and
   whether it's actually configured versus just available.
4. Check whether the specific request in question was even error/slow
   from the system's own perspective at the time (client-perceived
   slowness from network conditions outside any traced span wouldn't show
   up in server-side traces regardless of sampling).

## Fix

Move to (or add on top of existing head-based sampling) **tail-based or
outcome-biased sampling**: always keep traces for errors and requests
exceeding a latency threshold, and sample the remaining "boring" traffic
at a much lower rate -- this captures close to 100% of the traces that
are actually useful for debugging while still controlling total volume/
cost for the high-volume, low-information successful requests. If the
tracing backend doesn't support tail-based sampling natively, a
collector-level solution (e.g., an OpenTelemetry Collector with a tail
sampling processor) can sit in front of it. Revisit the sampling
percentage periodically against actual traffic growth, not just once at
initial setup.

## Pitfalls

Don't set the "always keep" latency threshold so low that it defeats the
volume control the sampling was meant to provide in the first place --
tune it against the service's actual latency distribution (e.g., p95/p99)
rather than a guessed round number. Also remember tail-based sampling
requires buffering spans until the trace completes, which needs more
collector memory/complexity than stateless head-based sampling --
budget for that operational cost rather than treating it as a free
upgrade.

## Verify

After switching to outcome-biased sampling, deliberately trigger a
synthetic error and a synthetic slow request in a non-prod (or carefully
scoped prod) test and confirm both are reliably captured as complete
traces, not just probabilistically present. Then confirm total trace
volume/cost stayed within the expected budget despite always keeping
errors and slow requests.
