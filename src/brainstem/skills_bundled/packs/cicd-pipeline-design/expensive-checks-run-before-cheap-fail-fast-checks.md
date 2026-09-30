---
name: expensive-checks-run-before-cheap-fail-fast-checks
description: A pipeline burns significant time on slow build and integration steps before running fast checks that could have failed the same commit in seconds.
triggers: ["ci wastes time before failing", "lint failure found after long build", "pipeline should fail faster", "expensive step runs before cheap check", "reorder pipeline stages for speed"]
permissions: ["READ"]
---

## Symptom
A commit with a trivial, fast-to-detect problem -- a lint violation, a
type error, a formatting issue, a unit test failure -- doesn't get
reported until many minutes into the pipeline run, because the pipeline
runs a full compile, a Docker image build, or a slow integration/E2E
suite first and only gets to the cheap static checks afterward (or in
parallel but the cheap check's failure doesn't short-circuit the
expensive ones already running). The developer waits far longer than
necessary to learn about a problem that a five-second check would have
caught immediately.

## Likely causes
1. **Stage order reflects the order the pipeline was written in, not
   cost/likelihood of failure** -- stages were added incrementally over
   time (build, then later a test stage, then later still a lint stage
   tacked on at the end) with nobody revisiting the overall ordering once
   all the pieces existed.
2. **No fail-fast configuration between stages** -- even where a cheap
   check exists early, the pipeline doesn't actually stop the rest of the
   run when it fails (missing `fail-fast: true` in a matrix, or later
   stages not conditioned on earlier stage success), so the expensive
   work proceeds regardless and the time is spent either way.
3. **The expensive step is bundled together with cheap checks in a single
   job/stage** rather than split out, so there's no boundary at which the
   pipeline engine could even short-circuit -- lint, type-check, and
   full build all happen sequentially inside one script in one job.
4. **A dependency-installation or environment-setup cost is paid before
   any check runs**, and that setup itself is slow, meaning even the
   "fast" checks are gated behind an expensive prerequisite that could be
   restructured (e.g. running lint in a lightweight job that only needs
   the linter installed, not the full application dependency tree).

## Diagnose
- Pull timing data per stage from recent pipeline runs and note, for each
  stage, both its typical duration and how often it's the one that
  actually fails, over a meaningful sample of runs.
- For runs that failed on a cheap check (lint/type/unit), measure the
  wall-clock time between commit push and the failure being reported --
  if this exceeds the cheap check's own standalone runtime by an order of
  magnitude, expensive work is running unnecessarily first or alongside
  without short-circuiting.
- Check the pipeline definition for explicit ordering/dependency
  declarations between stages, and check for `fail-fast` or equivalent
  short-circuit settings on any matrix or parallel job group.
- Identify what each early "fast" stage actually requires as a
  prerequisite (does lint need the full dependency install, or just the
  linter itself) to see whether setup cost can be decoupled per stage.

## Fix
Reorder the pipeline so stages run in ascending order of cost weighted by
likelihood of catching a real problem: static analysis and lint first
(fastest, catches the most common trivial mistakes), then type-checking,
then unit tests, then build, then slower integration/E2E tests last --
and make each stage a real dependency gate for the next (the pipeline
engine's native `needs`/stage-dependency mechanism), so a failure at any
point stops subsequent, more expensive stages from starting at all.
Where cheap checks don't actually need the full dependency/build
environment, give them their own lightweight job with minimal setup so
they can start and finish before the heavier environment even finishes
provisioning, rather than being stuck behind a shared setup step sized
for the most expensive stage.

## Pitfalls
- Making every stage strictly sequential (each waiting for the previous
  one's full completion) to get fail-fast ordering can reintroduce
  unnecessary serial time between checks that don't actually depend on
  each other's output (e.g. lint and type-check can usually run
  concurrently with each other, both before the build, rather than one
  after the other) -- order by dependency and cost, not by collapsing
  everything into one chain.
- Fail-fast is not always the right default for every context -- for a
  nightly full-regression run where the goal is a complete picture of
  every failure (not the fastest signal to a single developer), stopping
  at the first failure can hide other, unrelated problems that also
  needed fixing; scope fail-fast behavior to the fast-feedback CI-on-push
  context, not necessarily every scheduled/full-suite run.

## Verify
Introduce a deliberate lint violation in a test branch with no other
changes, push it, and measure the time until the pipeline reports
failure -- confirm it's close to the standalone lint step's own runtime
and that no expensive build/integration stage started or ran to
completion after the lint failure was known.
