---
name: circuit-breaker-outlier-detection-cascading-eviction
description: Istio's outlier detection ejects most or all instances of a backend service from the load-balancing pool at once, turning a partial slowdown into a total outage.
triggers: ["istio outlier detection ejecting all hosts", "circuit breaker cascading failure istio", "envoy ejected all upstream hosts", "outlier detection too aggressive"]
permissions: ["READ"]
---

## Symptom

During a period where a backend service is somewhat slow or returning an
elevated (but not universal) error rate, Istio's outlier detection
(circuit breaking) ejects most or all of that service's instances from
the load-balancing pool nearly simultaneously, turning a partial
degradation into a complete outage for callers of that service.

## Likely causes

- **Outlier detection thresholds are configured identically and
  independently per-instance**, so when a shared root cause (a database
  slowdown, a common downstream dependency issue) affects all instances
  similarly at roughly the same time, they all cross the ejection
  threshold together rather than one at a time.
- **The ejection threshold is too sensitive relative to the service's
  normal error-rate variance**, so a brief, correlated blip that would
  otherwise self-resolve triggers ejection before the service has a
  chance to recover on its own.
- **The base ejection time (how long an instance stays ejected) combined
  with a low `maxEjectionPercent` setting doesn't actually prevent
  ejecting effectively all capacity** -- if `maxEjectionPercent` is set
  too high (or defaults allow it), there's no floor protecting a minimum
  amount of serving capacity during a correlated event.
- **No shared, coordinated view exists across instances' outlier
  detection state** -- each Envoy proxy makes its ejection decision
  independently based on its own observed error rate toward each
  upstream instance, so there's no built-in mechanism to prevent a
  correlated pile-on beyond the percentage cap.

## Diagnose

1. Review the outlier detection configuration (`consecutiveErrors`/
   `consecutive5xxErrors`, `interval`, `baseEjectionTime`,
   `maxEjectionPercent`) on the relevant `DestinationRule` and compare
   against the service's normal baseline error rate and variance.
2. During or after an incident, check Envoy's ejection events/logs across
   multiple instances to confirm whether ejections happened in a tight
   time window (correlated) versus staggered.
3. Identify whether the underlying trigger was a shared root cause
   affecting all instances similarly (a common dependency) versus a
   genuinely instance-specific problem that outlier detection is
   correctly designed to catch.
4. Check `maxEjectionPercent`'s actual configured value against what
   percentage of instances were actually ejected during the incident.

## Fix

Tune outlier detection thresholds to tolerate the service's normal
short-term error-rate variance without triggering on brief, likely-self-
resolving blips, using `consecutiveErrors`/interval settings informed by
real historical data rather than defaults. Set `maxEjectionPercent` to a
value that guarantees a meaningful floor of serving capacity remains
even during a correlated event (e.g. capping ejection well below 100%),
accepting that some degraded instances may continue serving some traffic
rather than ejecting everything. For root causes that are genuinely
shared across all instances (a common downstream dependency), address
that dependency directly, since no amount of per-instance circuit-
breaker tuning fixes a shared root cause -- circuit breaking is meant for
isolating genuinely instance-specific problems.

## Pitfalls

Don't disable outlier detection entirely in response to a bad experience
with cascading ejection -- it's still valuable for catching genuinely
instance-specific failures (a single bad pod); the fix is tuning
thresholds and the ejection percentage cap, not removing the mechanism.
Also don't set thresholds so loose that outlier detection never
meaningfully protects against a truly failing individual instance,
overcorrecting in the opposite direction.

## Verify

Simulate a correlated slowdown/error-rate increase across all instances
of a test service (via fault injection) and confirm outlier detection no
longer ejects effectively all capacity, maintaining the configured
minimum serving floor. Separately confirm outlier detection still
correctly ejects a single deliberately-failing instance while leaving
healthy instances in the pool, proving the mechanism still works for its
intended genuinely-isolated-failure case.
