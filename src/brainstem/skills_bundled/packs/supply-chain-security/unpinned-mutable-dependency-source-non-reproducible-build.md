---
name: unpinned-mutable-dependency-source-non-reproducible-build
description: The same commit produces different, unreproducible build artifacts on different runs because dependencies resolve from a moving Docker tag or unpinned version range.
triggers: ["build is different every time even with the same code", "docker image tag changed content unexpectedly", "cannot reproduce a build from months ago", "latest tag pulled a different image than before", "builds not reproducible supply chain risk"]
permissions: ["READ"]
---

## Symptom
Building from the exact same commit at two different points in time (or
on two different machines at the same time) produces artifacts with
different dependency versions baked in, even though nothing in the
source repository changed. This surfaces as "it worked in CI yesterday,
fails today with no code change," a production incident that can't be
reproduced locally because the build pulled different base image or
package versions than what's actually deployed, or -- in the worst case
-- a window in which a build silently picked up a swapped-in malicious
version of something the team believed was fixed.

## Likely causes
1. **A Docker base image is referenced by a mutable tag** (`node:20`,
   `python:3.11`, or worse, `latest`) rather than a content-addressable
   digest -- the tag can be repointed by the image publisher at any time,
   so the "same" `FROM` line resolves to genuinely different bytes on
   different days.
2. **Package version ranges are unpinned in the manifest** (`^1.2.0`,
   `>=2.0`, no lockfile committed, or a lockfile that exists but isn't
   actually used by the install command) so dependency resolution
   re-runs against the live registry state on every build rather than
   against a frozen, known set of versions.
3. **A lockfile exists and is correct, but the build process doesn't
   honor it** -- e.g. running `npm install` instead of `npm ci`, or a
   custom build script that regenerates the lockfile instead of
   installing strictly from the committed one.
4. **CI caches are keyed loosely enough that a stale or wrong cache entry
   gets reused across builds that should be independent**, masking the
   non-reproducibility in one direction while introducing a different
   inconsistency (a build using cached dependencies that no longer match
   the current lockfile at all).

## Diagnose
- Grep all `Dockerfile`/`docker-compose` files for `FROM` lines using a
  tag rather than a `@sha256:` digest, and grep CI config for base images
  referenced the same way.
- Check whether a lockfile is committed to the repository at all, and if
  it is, check the exact install command used in CI (`npm install` vs.
  `npm ci`, `pip install -r requirements.txt` vs. a hash-verified
  `pip-compile`/`pip install --require-hashes` flow) -- confirm the
  command used actually enforces the lockfile rather than treating it as
  advisory.
- Run the build twice in immediate succession in clean, isolated
  environments and diff the resulting dependency tree (`npm ls --all` or
  equivalent) between the two runs -- any difference with no source change
  confirms non-reproducibility right now, not hypothetically.
- Check image registry history for the base image tag in use (most
  registries show digest history per tag) to confirm whether it has
  actually been repointed to different content over the build's lifetime.

## Fix
Pin Docker base images by digest (`FROM node:20@sha256:...`) rather than
by tag, updating the digest deliberately as part of a reviewed change
rather than allowing it to drift silently -- this makes base image
updates an explicit, auditable commit instead of an invisible moving
target. For application dependencies, commit the lockfile and use the
install command variant that enforces it strictly (`npm ci`, `poetry
install --sync`, `pip install --require-hashes`) in every build
environment, including local dev, so there is exactly one source of truth
for exact versions. Where the ecosystem supports it, use hash-verification
(not just version-pinning) so even a same-version-different-content
substitution at the registry level is caught rather than silently
accepted. Treat any CI cache as an optimization layered on top of this
reproducible baseline, keyed strictly on lockfile hash, never as a
substitute for pinning.

## Pitfalls
- Pinning application dependency versions in the manifest but leaving the
  Docker base image on a mutable tag -- both layers need pinning
  independently; fixing one and assuming the whole build is now
  reproducible leaves the other as an active supply-chain swap vector.
- Committing a lockfile but never actually verifying the build command
  enforces it -- a lockfile that the install step silently regenerates or
  ignores provides no real protection despite looking like a best
  practice in the repository.
- Pinning everything once and never revisiting it -- indefinitely frozen
  dependencies accumulate the same security debt this pack's other skills
  warn about; the goal is deliberate, reviewed updates, not permanent
  immutability.

## Verify
Build from the same commit twice, in separate clean environments (or a
few days apart), and diff the resulting dependency tree and base image
digest actually used in each -- they must be identical. Confirm the
Dockerfile's `FROM` line resolves to a fixed digest by inspecting the
built image's layer history rather than trusting the tag name alone.
Confirm the install command's exit behavior when the lockfile and
manifest are made to disagree deliberately (e.g. hand-edit one version in
the lockfile) -- a properly enforcing install command should fail loudly
rather than silently re-resolving.
