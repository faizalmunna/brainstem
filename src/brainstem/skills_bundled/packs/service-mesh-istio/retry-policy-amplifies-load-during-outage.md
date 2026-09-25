---
name: retry-policy-amplifies-load-during-outage
description: An Istio VirtualService retry policy multiplies request volume toward an already-struggling backend during a partial outage, making the outage worse instead of masking transient errors.
triggers: ["istio retries making outage worse", "virtualservice retry policy amplifying load", "envoy retry storm", "mesh retries overwhelming backend during incident"]
permissions: ["READ"]
---

## Symptom

During a partial outage or significant slowdown of a backend service, the
actual load reaching that backend is higher than the nominal client
request rate would suggest, and the backend's recovery is slower or less
likely than expected -- traced back to an Istio `VirtualService` retry
policy automatically retrying failed/slow requests, multiplying effective
load during exactly the period the backend can least handle it.

## Likely causes

- **A retry policy configured with a fixed retry count and no backoff**
  means every failing request is immediately retried some fixed number of
  times, multiplying total request volume toward a backend that's
  already failing under normal load, let alone amplified load.
- **Retries are configured on `5xx`/`connect-failure` conditions without
  considering that a struggling backend returning `5xx` under overload is
  exactly the condition where retrying makes things worse, not better** --
  retries are most valuable for transient, independent failures, not for
  systemic overload.
- **No circuit breaker or outlier detection is configured alongside
  retries**, so there's no mechanism to reduce load toward a clearly
  struggling backend even as retries keep adding to it.
- **Retry policies are applied uniformly across many services calling the
  same struggling backend**, so even a individually-reasonable-looking
  retry count multiplies significantly in aggregate across all callers
  during a shared incident.

## Diagnose

1. During or after an incident, compare the actual request rate observed
   at the struggling backend against the nominal client-side request rate
   -- a significant multiplier confirms retry amplification.
2. Check the `VirtualService` retry configuration (`attempts`,
   `retryOn`, and whether `retryBackoff` is configured) for the affected
   service calls.
3. Check whether circuit breaking / outlier detection is configured
   alongside retries for the same destination, or whether retries are
   the only resilience mechanism in place.
4. Identify how many distinct calling services/paths have their own
   independent retry policies targeting the same struggling backend, to
   quantify the aggregate amplification effect.

## Fix

Configure retry policies with appropriate backoff (`retryBackoff` with a
base interval and cap) rather than immediate fixed-count retries, and
scope `retryOn` conditions to genuinely transient failure types rather
than blanket-retrying every `5xx`. Pair retries with circuit breaking/
outlier detection on the same destination, so a backend that's clearly
struggling gets some callers' traffic reduced rather than uniformly
amplified by every caller's independent retries. Consider a mesh-wide
or shared retry budget concept (bounding total retry volume across
callers) for critical shared backends where many independent retry
policies could otherwise compound during a shared incident.

## Pitfalls

Don't remove retries entirely in response to this discovery -- retries
are genuinely valuable for transient, independent failures (a single
dropped packet, a brief GC pause) and removing them reduces resilience
for the common case to fix a less common but more severe amplification
scenario; the fix is backoff and pairing with circuit breaking, not
elimination. Also don't tune retry policy for just the one service that
caused a visible incident while leaving the same aggressive
no-backoff pattern in place for other services calling other shared
backends.

## Verify

Simulate a backend slowdown/partial failure in a non-prod environment
with the updated retry/circuit-breaker configuration and confirm the
effective load multiplier toward the backend stays bounded and doesn't
compound the original degradation. Confirm retries still correctly
recover a genuinely transient, isolated failure in the same test setup.
