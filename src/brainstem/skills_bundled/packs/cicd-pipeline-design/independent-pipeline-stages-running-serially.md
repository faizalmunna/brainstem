---
name: independent-pipeline-stages-running-serially
description: A pipeline runs two stages one after another that have no actual dependency on each other, needlessly stretching out total pipeline time.
triggers: ["pipeline slower than it needs to be", "jobs running one after another unnecessarily", "ci taking too long total time", "stages could run at the same time", "speed up pipeline by parallelizing"]
permissions: ["READ"]
---

## Symptom
The end-to-end pipeline takes noticeably longer than the sum of critical
work actually requires, because stages that don't depend on each other's
output (e.g. unit tests and a linter, or a frontend build and a backend
build) execute one after the other rather than concurrently -- inspecting
the timeline shows long stretches where only one job is running and the
runner fleet is otherwise idle.

## Likely causes
1. **The pipeline was authored as a simple linear list of steps** (common
   when a pipeline grows incrementally, each new stage appended after the
   last) without anyone modeling actual data dependencies between stages,
   so execution order reflects authoring order, not real requirements.
2. **A shared, unnecessarily coarse resource or job artifact creates an
   artificial dependency** -- e.g. both stages are defined inside the same
   job/step sequence so the CI system has no way to know they could
   split, even though their actual inputs don't overlap.
3. **Real dependencies exist for only *some* outputs of an earlier stage**,
   and the whole stage was made a blocking prerequisite for simplicity --
   e.g. a "build" stage produces both a Docker image (needed by deploy)
   and a coverage report (needed by nothing downstream), but a later
   independent stage waits on the entire build job rather than just the
   artifact it actually needs.
4. **The CI system's parallelism is capped by runner/concurrency limits**
   rather than the pipeline definition -- stages are declared as
   independent (correctly), but the account/plan's concurrent-job limit
   or a shared runner pool serializes them anyway, which looks identical
   to a serial pipeline definition from the total-time graph alone.
5. **Fear of flaky shared state** -- someone previously hit a race
   condition when two stages ran concurrently (e.g. both writing to the
   same test database or cache path) and the fix applied was to force
   them serial globally, rather than isolating the actual shared
   resource.

## Diagnose
- Pull the pipeline's stage/job timeline view (most CI systems visualize
  this -- GitHub Actions' job graph, GitLab's pipeline graph, Jenkins'
  Blue Ocean view) and identify stages with zero data dependency between
  them that are nonetheless sequential.
- For each candidate pair, explicitly trace what each stage consumes as
  input and produces as output -- if stage B doesn't read anything stage
  A wrote (no shared artifact, no shared generated file), the ordering is
  arbitrary, not required.
- Check the account/runner concurrency configuration (max parallel jobs)
  separately from the pipeline YAML's dependency declarations -- a
  correctly-parallelized pipeline definition can still execute serially
  if capped at one concurrent runner.
- If serial ordering was intentional, search version history/commit
  messages for why (often a past incident) to distinguish "nobody thought
  about it" from "this was deliberately serialized to avoid a race,"
  which need different fixes.

## Fix
Model the pipeline as an explicit dependency graph rather than a script:
declare each stage's real inputs and outputs, and let the CI system's
native parallel-stage/job mechanism (`needs:` in GitHub Actions, `needs:`
/DAG mode in GitLab CI, parallel stages in Jenkins declarative pipelines)
run everything without a genuine dependency edge concurrently. Where a
stage was serialized only because it shares a job with another stage for
convenience, split them into separate jobs so the scheduler can place
them concurrently. Where serialization exists to avoid a real shared-state
race (a shared test database, a shared file path), fix the actual
resource contention (isolated database schemas/containers per job,
unique temp paths) instead of keeping the whole pipeline serial.

## Pitfalls
- Parallelizing stages that share a hidden resource (a test database, a
  port, a cache directory) without isolating that resource first
  introduces flaky, hard-to-reproduce failures that are worse than the
  slow pipeline being fixed -- always audit for shared state before
  flipping stages to run concurrently.
- Maximizing parallelism without regard for runner cost/quota can trade
  wall-clock time for a much larger compute bill or hit concurrency caps
  that cause queuing delays elsewhere, which can net out slower for the
  team's actual CI queue even though any single pipeline run looks
  faster in isolation.

## Verify
Compare the pipeline's total wall-clock duration before and after the
change across several runs, and inspect the stage timeline graph to
confirm the previously-serial stages now show overlapping start/end
times -- and rerun the suite several times to confirm no new
intermittent failures appear from the newly-concurrent execution.
