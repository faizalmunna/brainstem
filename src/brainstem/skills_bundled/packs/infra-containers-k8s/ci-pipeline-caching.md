---
name: ci-pipeline-caching
description: Speed up a slow CI/CD pipeline by fixing broken or missing dependency/build caching, instead of just throwing more compute at it.
triggers: ["ci pipeline slow", "github actions slow", "ci cache not working", "build takes too long ci", "speed up ci pipeline"]
permissions: ["READ"]
---

## Symptom
A CI pipeline (GitHub Actions, GitLab CI, etc.) takes noticeably longer
than the actual work it's doing should require -- reinstalling
dependencies from scratch every run, rebuilding unchanged layers/
artifacts, or repeating the same expensive step across every job in a
matrix without sharing results.

## Likely causes
1. **No dependency cache configured at all** (or a cache key that never
   actually hits), so every run reinstalls the full dependency tree from
   the network from scratch.
2. **A cache key too broad or too narrow**: too broad (e.g. keyed only on
   branch name) serves a stale cache that doesn't reflect a real
   dependency change; too narrow (e.g. keyed on a timestamp) never hits
   at all, providing no benefit despite the caching code being present.
3. **Docker layer caching not utilized in CI** -- each build starts from
   scratch even though most layers (base image, dependency install)
   haven't changed since the last build.
4. **Redundant work repeated across matrix jobs** (e.g. every OS/version
   combination in a test matrix independently reinstalling the same
   dependencies) without a shared setup step or cache scoped to allow
   reuse across the matrix.
5. **Artifacts rebuilt from scratch across pipeline stages** (build,
   test, deploy) instead of building once and passing the built artifact
   forward.

## Diagnose
- Check the pipeline's cache configuration (or absence of one) for
  dependency installation steps, and check the CI provider's cache-hit/
  miss reporting (most CI systems log this) across recent runs.
- Inspect the cache key expression: does it include a hash of the actual
  lockfile/dependency manifest (correct) or something unrelated/too
  coarse (branch name, a static string)?
- Time each pipeline stage across several runs to identify which step
  actually dominates total time -- optimize the biggest contributor
  first, not the first thing noticed.

## Fix
- Cache dependencies keyed on a hash of the lockfile (`package-lock.json`,
  `poetry.lock`, `Cargo.lock`, etc.), with a fallback restore key on a
  broader prefix so a partial cache hit (an older version of the lockfile)
  still saves most of the work when an exact hit isn't available.
- Enable Docker layer/build caching in CI (registry-based cache, or the
  CI provider's native Docker layer cache) so unchanged layers (base
  image, dependency-install layer when the lockfile hasn't changed)
  aren't rebuilt every run.
- Build once and pass the artifact between pipeline stages/jobs (using
  the CI system's artifact-passing mechanism) instead of rebuilding the
  same output in each stage.
- For matrix builds, share a single dependency-install/cache-population
  step where the dependency set is identical across the matrix
  dimensions, or ensure the cache key allows reuse across matrix legs
  that don't actually differ in dependencies.

## Pitfalls
- An overly broad cache key can serve stale dependencies after a real
  lockfile change if the key doesn't actually include that file's hash --
  always verify the cache actually invalidates when the lockfile changes,
  not just that it hits fast when unchanged.
- Caching build output (not just dependencies) across code changes can
  serve a stale build if the cache key doesn't account for source changes
  -- scope build-output caching carefully, or prefer caching only
  dependencies/toolchains and always rebuilding the actual application
  code.

## Verify
Make a real dependency change (bump one package version) and confirm the
cache correctly misses and reinstalls just for that change, then make an
unrelated code-only change and confirm the dependency cache correctly
hits and the pipeline time drops close to the baseline expected from
skipping dependency installation.
