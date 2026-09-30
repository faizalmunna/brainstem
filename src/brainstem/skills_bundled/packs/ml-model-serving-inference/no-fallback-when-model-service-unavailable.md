---
name: no-fallback-when-model-service-unavailable
description: An application feature depending on a model serving endpoint fails completely (rather than degrading gracefully) when that endpoint is temporarily unavailable or slow.
triggers: ["model service down breaks whole feature", "no fallback for inference failure", "ml service outage cascades to application", "inference timeout no graceful degradation"]
permissions: ["READ"]
---

## Symptom

A model serving endpoint becomes temporarily unavailable (a deploy, an
outage, a timeout under load), and every application feature depending
on it fails completely -- a hard error surfaced to the user, or a
cascading failure into other parts of the application -- rather than
degrading gracefully to some acceptable reduced-functionality state.

## Likely causes

- **The application code treats the model inference call as a required,
  blocking dependency with no fallback path**, so any failure or timeout
  propagates directly as a feature failure, the same way a required
  database call failing would.
- **No default/fallback behavior was designed for the specific feature**
  (a static default recommendation, a simpler rule-based heuristic, a
  cached previous result) that could substitute for a live model
  response when the model service is unavailable.
- **Timeout configuration for the model service call is too long or
  absent**, so a slow/struggling model service holds up the entire
  request for an extended period rather than failing fast enough to
  trigger a fallback within an acceptable overall response time budget.
- **The model service being unavailable wasn't considered a realistic
  failure mode during design**, treating ML inference as if it had the
  same reliability guarantees as core infrastructure, when in practice
  model serving often has different (sometimes lower) availability
  characteristics, especially for newer or less battle-tested
  deployments.

## Diagnose

1. Identify every application feature with a hard dependency on model
   inference and check whether each has any fallback behavior defined.
2. Check the actual timeout configuration for model service calls
   relative to the overall feature's acceptable response time budget.
3. Review incident history for the model service's actual availability/
   latency track record, to understand how often this failure mode is
   realistically likely to matter.
4. For the specific feature that failed, determine what an acceptable
   degraded experience would look like (no personalization instead of an
   error, a cached recent result, a simpler heuristic).

## Fix

Design and implement an explicit fallback for each feature depending on
model inference -- a sensible default, a cached previous result, or a
simpler non-ML heuristic -- so the feature degrades gracefully rather
than failing outright when the model service is unavailable or too slow.
Set a tight, explicit timeout on model service calls sized to the
feature's actual response time budget, triggering the fallback path
promptly rather than waiting indefinitely. Treat model service
availability as a realistic failure mode in system design from the start,
the same way any other external dependency would be treated, rather than
assuming it will always be available.

## Pitfalls

Don't implement a fallback so generic that it silently produces a
meaningfully worse experience without anyone noticing -- track fallback
activation as its own metric (how often does the feature actually run in
degraded mode) so the team has visibility into how often this is
happening and whether the underlying model service reliability needs
separate attention.

## Verify

Deliberately make the model service unavailable in a test environment
(or via a feature flag simulating failure) and confirm the dependent
feature degrades gracefully to its fallback behavior rather than
failing outright. Confirm fallback activation is tracked and visible in
monitoring so real-world occurrences are known, not just tested once.
