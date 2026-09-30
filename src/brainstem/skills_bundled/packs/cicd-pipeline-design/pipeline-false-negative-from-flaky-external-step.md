---
name: pipeline-false-negative-from-flaky-external-step
description: A pipeline fails intermittently due to a transient issue in an external dependency step, unrelated to any actual code defect, eroding trust in the pipeline.
triggers: ["ci fails randomly for no reason", "flaky pipeline unrelated to my code", "intermittent network error in ci", "pipeline failed then passed on rerun with no changes", "package download timeout in ci"]
permissions: ["READ"]
---

## Symptom
A pipeline run fails, but the failure has nothing to do with the code
change being tested -- a package registry timeout, a transient DNS
resolution failure, a flaky third-party API call in an integration test,
or a container registry rate limit -- and simply re-running the exact
same commit passes. Over time, engineers start reflexively re-running
red pipelines without reading why, which means a real failure buried
among the noise gets the same "just rerun it" treatment and slips
through.

## Likely causes
1. **Network-dependent steps have no retry logic** -- a single dependency
   download, external API call, or registry pull is attempted exactly
   once with no backoff/retry, so any transient blip anywhere in that
   network path (DNS, TLS handshake, a momentary 503 from the registry)
   fails the entire pipeline run outright.
2. **Shared external services are rate-limited or have availability SLAs
   below what the pipeline assumes** -- a public package registry, a
   third-party API used in integration tests, or a shared CI runner
   pool's own dependency mirror occasionally throttles or hiccups under
   normal operation, and the pipeline was never designed with that
   reality in mind.
3. **No distinction is made between infrastructure failures and test
   assertion failures in the pipeline's reporting** -- both surface as
   a plain red "failed" status, so there's no way to see at a glance
   whether a given failure is "network timeout downloading a dependency"
   versus "assertion mismatch in test X," which is what actually drives
   the reflexive-rerun behavior in the first place.
4. **A test that's flaky for reasons unrelated to network** (real timing
   race, shared mutable test state, order-dependence) gets misdiagnosed
   as "just infra flake" and lumped into the same "ignore and rerun"
   bucket, when it actually indicates a real, code-level bug that
   deserves investigation.

## Diagnose
- Collect failure logs across recent flaky runs and bucket them by
  failure signature (exact error string/stack), not just "pipeline
  failed" -- this separates genuinely different root causes that were
  being treated as one undifferentiated "flakiness" problem.
- For network-attributed failures, check whether the failing step retries
  at all, and if so, how many attempts/what backoff -- a step retried
  zero or one time is far more exposed to transient blips than one with
  even minimal exponential backoff.
- Check whether the flaky step depends on an external network resource
  outside the team's control (public registry, third-party API) versus
  an internal resource (another team's shared staging environment, a
  shared test database) -- the fix differs for each.
- Track failure rate over time per pipeline step (most CI systems expose
  step-level history) to find which specific step accounts for the
  majority of "reran and passed" outcomes, rather than treating the whole
  pipeline as uniformly flaky.

## Fix
Add bounded retry with exponential backoff specifically to steps that
call external network resources (dependency installs, registry pulls,
external API calls in tests) at the step level, so a single transient
blip self-heals without a human needing to notice and manually rerun the
whole pipeline. Where a dependency has a stable public source, mirror or
cache it internally (an internal package proxy/registry mirror) to
reduce exposure to that external service's own availability. Separately,
tag/report infrastructure-category failures distinctly from assertion
failures in the pipeline's output (a distinct exit code, a labeled
failure category) so a real code-level failure is never visually
indistinguishable from a known-flaky network step, and track a
flaky-step allowlist explicitly rather than let "just rerun" become the
undocumented default response to any red build.

## Pitfalls
- Retrying indiscriminately, including around assertions that are
  legitimately failing due to a real bug, hides genuine regressions
  behind a "it passed on retry 2" result -- scope automatic retry to
  specifically-identified external/network operations, never to the
  test's actual assertions.
- Building an informal team culture of "always rerun failed pipelines
  before looking at them" without ever fixing the underlying flaky steps
  is the actual failure mode this skill addresses -- retries and mirrors
  should reduce the *rate* of transient failures toward zero, not become
  a permanent crutch that normalizes ignoring red pipelines.

## Verify
After adding retry/backoff or an internal mirror to the identified flaky
step, track that step's failure rate over the next several weeks of real
runs and confirm it drops close to zero, and confirm that a deliberately
introduced real test failure (an intentionally wrong assertion in a
throwaway branch) still fails the pipeline every time with no retry
masking it.
