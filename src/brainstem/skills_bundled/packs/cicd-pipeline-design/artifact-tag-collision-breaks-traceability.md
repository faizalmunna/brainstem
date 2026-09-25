---
name: artifact-tag-collision-breaks-traceability
description: Two different commits produce build artifacts with the same version tag, making it impossible to trace a deployed artifact back to the exact source that produced it.
triggers: ["can't tell which commit is deployed", "artifact tag reused for different commits", "docker image tag overwritten by another build", "same version number two different builds", "cannot trace deployed version to source"]
permissions: ["READ"]
---

## Symptom
An incident review or audit needs to know exactly which source commit
produced the artifact currently running in production, but the version
tag on that artifact (a Docker image tag, a package version, a build
number) turns out to correspond to more than one commit -- a later build
silently overwrote an earlier one under the same tag, or the tag was
generated in a way that doesn't uniquely determine the commit at all.

## Likely causes
1. **Mutable tags used as the deploy reference** -- builds are tagged
   `latest`, a branch name (`main`), or a manually-bumped semantic version
   that isn't automatically tied to a commit, and each new build on that
   branch overwrites the same tag in the registry, so the tag now points
   at whichever commit built most recently.
2. **Version derived from something that isn't commit-unique** -- e.g. a
   date-based or build-number-based tag that resets, collides across
   parallel pipeline runs, or is computed from a source that two
   different commits can both produce (a version bumped by hand in a file
   that two branches both left at the same value).
3. **Retagging/promotion between environments loses the original
   identity** -- an artifact is rebuilt (not promoted as the same binary)
   at each pipeline stage (dev, staging, prod), so the "same version" seen
   in each environment is actually three different builds that happen to
   share a human-assigned label, and a non-deterministic build step
   (unpinned dependency, embedded timestamp) makes them not even bit-
   identical.
4. **Concurrent pipeline runs racing on the same tag** -- two commits
   pushed close together both compute the same version string (e.g. both
   read the same "next version" counter before either incremented it) and
   whichever build finishes last wins the registry push, silently
   discarding the other.

## Diagnose
- Pick a currently-deployed artifact tag and check the registry's
  push history for that exact tag/digest -- most registries retain a
  content digest (e.g. Docker's `sha256:...`) separately from the human
  tag; check whether multiple pushes share the tag but have different
  digests, which directly proves tag reuse.
  the tag was applied, and confirm whether that commit's build actually
  matches what's running (rebuild it locally/in CI and compare digests).
- Check the version/tag-generation logic in the pipeline: does it derive
  the tag from an immutable, unique input (full commit SHA) or from
  something mutable/reusable (branch name, hand-edited version file, a
  counter)?
- Look for retag/promote steps between environments and check whether
  they reference the same immutable digest end-to-end or trigger a fresh
  build at each stage.

## Fix
Make the artifact's identity derive from something that is unique and
immutable by construction, not something assigned by convention: tag
every build with the full source commit SHA (or a content-addressed
digest) as the primary, non-reused identifier, and treat human-friendly
version strings (semver, `latest`, environment names) as *additional*
pointers layered on top -- never as the sole reference used to promote or
deploy. Promote the same built artifact (by digest) through environments
rather than rebuilding at each stage, so "what's in staging" and "what's
in prod" refer to the literal same bytes, not two separate builds that
happen to share a label. Record the commit SHA -> artifact digest mapping
somewhere queryable (build metadata, a deploy manifest, or the registry's
own tag-to-digest history) so tracing a running artifact back to source
is a lookup, not an investigation.

## Pitfalls
- Switching to commit-SHA tags but keeping a mutable `latest`-style tag
  as the thing deployment actually references reintroduces the exact
  ambiguity being fixed -- `latest` must never be what a deploy pipeline
  or runbook uses to identify what's running.
- Assuming a semantic version bump alone (without a commit SHA attached)
  solves this -- two different commits can still be assigned the same
  hand-chosen semver if the bump is manual and not enforced/validated
  against the actual last-released version in CI.

## Verify
Take the artifact currently deployed to production, extract its content
digest, look up the commit SHA recorded for that digest in build
metadata, check out that exact commit, rebuild it through the same
pipeline, and confirm the resulting digest matches -- this proves the
recorded mapping is accurate rather than just present.
