---
name: memory-growth-only-under-specific-request-pattern
description: A memory leak only manifests under a specific, infrequent request pattern or code path, making it invisible in general load testing and hard to reproduce on demand.
triggers: ["memory leak only certain requests", "intermittent memory growth specific endpoint", "cannot reproduce memory leak in testing", "leak only happens under rare condition"]
permissions: ["READ"]
---

## Symptom

A memory leak is confirmed to exist in production (via steadily
increasing memory usage over long time periods) but general load testing
and typical development usage never reproduces it -- the leak only
manifests under a specific, relatively rare request pattern, input
shape, or sequence of operations that doesn't show up in standard
testing.

## Likely causes

- **The leak is triggered by a specific, infrequent code path** (an
  error-handling branch, a rarely-used feature, a specific input edge
  case) that standard load testing with typical/happy-path traffic never
  exercises with enough volume to make the leak visible in a short test
  window.
- **The leak requires a specific sequence of operations** (create-then-
  cancel, open-then-fail-to-close-in-a-specific-order) rather than any
  single operation in isolation, making it invisible to tests that only
  exercise operations independently.
- **The leak scales with a request characteristic that's rare in test
  data but occurs at meaningful volume in real production traffic** (a
  specific large payload size, a specific combination of query
  parameters), so small-scale testing with typical inputs doesn't
  trigger enough accumulation to be noticeable.
- **Standard load tests run for too short a duration to reveal a slow
  per-request leak** that only becomes visible in aggregate after many
  hours or days of the specific pattern occurring repeatedly.

## Diagnose

1. Analyze production logs/metrics for what's actually correlated with
   memory growth periods -- specific endpoints, specific error rates,
   specific traffic characteristics -- to narrow down the triggering
   pattern.
2. Once a candidate pattern is identified, construct a targeted test that
   specifically and repeatedly exercises that pattern (not general load)
   and monitor memory during that targeted test.
3. If the pattern involves a specific sequence, test that exact sequence
   in isolation and compare against testing each operation independently,
   to confirm the sequence-dependence.
4. Extend the targeted test's duration/repetition count if a single leak
   instance is small, since a slow per-occurrence leak needs enough
   repetitions to become measurable.

## Fix

Once the specific triggering pattern is reproduced in an isolated test,
apply standard leak diagnosis (heap/resource profiling during the
targeted test) to identify and fix the actual leaking reference/resource,
using the same techniques as a general leak but now with a reliable
reproduction case. Add the specific triggering pattern as a permanent
addition to the load-testing or regression-testing suite going forward,
so this exact class of leak (and similar future ones triggered by rare
patterns) has a better chance of being caught before reaching production.

## Pitfalls

Don't give up on reproducing a suspected rare-pattern leak too early and
resort to purely production-based mitigation (frequent restarts) without
first genuinely attempting to isolate and reproduce the triggering
pattern -- a reproducible test case makes the actual fix far more
tractable and verifiable than working blind against production alone.

## Verify

Run the targeted reproduction test with the fix applied and confirm
memory no longer grows under the specific pattern that previously
triggered it. Deploy to production and monitor the specific
previously-affected metric/endpoint over an extended period to confirm
the leak is genuinely resolved in the real environment, not just the
isolated test.
