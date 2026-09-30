---
name: canary-rollout-ignores-elevated-error-rate
description: A canary deployment keeps auto-promoting to 100% traffic even though the canary slice shows a clearly elevated error rate.
triggers: ["canary rolled forward despite errors", "canary deployment auto-promoted with bad metrics", "canary auto-promote ignoring error rate", "progressive rollout didn't stop on regression", "canary analysis didn't block promotion"]
permissions: ["READ"]
---

## Symptom
A canary deployment (e.g. 5% -> 25% -> 50% -> 100% traffic) proceeds all
the way to full rollout even though the canary cohort's error rate, p99
latency, or crash rate was visibly worse than baseline the entire time.
The bad version reaches 100% of production before a human notices and
manually rolls back -- the automation that was supposed to catch this
never fired.

## Likely causes
1. **No automated gate actually exists between stages** -- the pipeline
   has timed sleeps between traffic-percentage bumps (e.g. "wait 10
   minutes, then promote") with no query against the canary's metrics at
   all; the canary dashboard exists for humans to *watch*, not for the
   pipeline to *act on*.
2. **The gate queries the wrong metric scope** -- it checks the overall
   service error rate (baseline + canary combined) instead of the
   canary's own tagged/labeled slice, so a small canary's errors are
   diluted into noise against the much larger stable population and never
   cross the threshold.
3. **The threshold or comparison window is miscalibrated** -- an absolute
   error-rate threshold that's higher than the service's real baseline
   noise, or a comparison window so short that normal traffic variance
   frequently exceeds it (so it was previously loosened or disabled after
   crying wolf), or a window so long that a fast-onset regression is
   averaged away before the window closes.
4. **The analysis step runs but its failure doesn't stop the pipeline** --
   the canary-analysis job reports "failed" or emits a low score, but the
   next stage isn't actually conditioned on that job's exit status/output
   (e.g. `continue-on-error: true` left over from debugging, or the
   promotion step is a separate manually-triggered job that ignores
   upstream state).
5. **Metrics lag behind the promotion decision** -- the pipeline checks
   metrics immediately after shifting traffic, before the monitoring
   system's scrape/aggregation interval has produced a data point for the
   new traffic split, so it evaluates stale (pre-shift) data and sees no
   regression.

## Diagnose
- Open the pipeline definition for the rollout stage and find the literal
  condition that gates the next traffic bump. If it's `sleep` / a fixed
  timer with no query, there is no automated gate -- confirm this first
  before looking anywhere else.
- If there is a query, run it by hand for the time window of a known bad
  rollout and check whether it's actually filtered to the canary's
  version/revision label versus the whole service.
- Pull the actual metric values from that incident's canary window and
  compare them against the configured threshold and window length --
  compute whether the regression would have crossed the threshold given
  the window size actually configured.
- Check the analysis job's run history (Argo Rollouts AnalysisRun,
  Flagger canary CR, or equivalent) for that incident: did it report a
  failing verdict, and if so, trace what the next pipeline stage did with
  that verdict -- did it block, or proceed anyway.
- Check the monitoring backend's scrape/aggregation interval versus the
  delay the pipeline waits after each traffic shift before querying --
  if the wait is shorter than one full aggregation interval, the pipeline
  is structurally querying stale data.

## Fix
Treat the canary gate as a hard dependency the promotion step cannot
bypass, not an advisory dashboard: use a canary-analysis primitive
(Argo Rollouts `AnalysisTemplate`, Flagger, or a custom step) that queries
metrics scoped explicitly to the canary revision (by pod label, version
tag, or separate metric stream), compares against a **relative** baseline
(canary vs. concurrently-measured stable, not canary vs. a static
historical number) over a window at least as long as the metrics
backend's aggregation interval, and make the next stage's execution
conditional on that analysis's pass/fail output at the pipeline-engine
level (a real dependency edge), not a convention that a human or a later
step is expected to respect.

## Pitfalls
- Setting the error-rate threshold so tight that normal traffic variance
  trips it regularly teaches the team to ignore or disable the gate --
  calibrate the threshold against several weeks of real baseline noise,
  not a round number picked arbitrarily.
- Adding the analysis step but leaving a manual "force promote" button
  wired to the same pipeline without also requiring the same gate,
  which becomes the path everyone actually uses under time pressure and
  quietly reintroduces the original bug.

## Verify
Inject a synthetic regression into a non-production canary run (e.g. a
feature-flagged handler that returns 500 for a fraction of requests) and
confirm the pipeline automatically halts and rolls back the canary
without any human intervention, with the analysis job's failing verdict
visible in the pipeline's run log as the actual cause of the halt.
