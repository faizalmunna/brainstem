---
name: upgrade-bug-not-reproducible-because-ci-prod-versions-differ
description: A post-upgrade bug cannot be reproduced locally or in CI because each environment installed different dependency versions, so the same code pulls a different transitive or platform build in each place.
triggers: ["works on my machine but breaks in prod after upgrade", "can't reproduce the upgrade bug in CI", "dependencies resolved differently in CI and production", "install pulled different versions locally and in prod"]
permissions: ["READ"]
---

## Symptom

After a dependency upgrade, production exhibits a bug that cannot be
reproduced in CI or on a developer machine -- same source, same manifest,
different behavior. Re-running the upgrade attempt reproduces nothing, or
occasionally reproduces the wrong thing. The environments resolved
*different actual versions or different platform variants* of the same
dependency: a loose or floating constraint resolved to a different snapshot
in each place, or each platform selected a different binary target than the
one production ships.

## Likely causes

- **No committed lockfile, or a lockfile that isn't actually honored**
  (manifest bumped but lockfile not regenerated, `requirements.txt`/
  equivalent floats, a Docker build that re-resolves rather than installing
  locked), so every environment resolves independently at its own point in
  time.
- **Loose version constraints** (`>=`, `^`, unpinned ranges) that resolve
  to "whatever is newest at install time" -- which differs between local
  (installed last month), CI (installed last night), and prod (installed
  when the image was built, possibly weeks ago).
- **Platform-specific resolution:** the dependency ships different
  artifacts per OS, CPU, interpreter version, or base image (native wheels,
  prebuilt binaries, Node ABI versions), so the developer laptop tests a
  different artifact than the production container.
- **An asymmetric cache:** CI or local serves a cached older resolution
  while a fresh container build (or vice versa) pulls the new one, making
  the divergence a function of which cache expired rather than of the code.

## Diagnose

1. Compare the resolved dependency set across local, CI, and the deployed
   artifact (`pip freeze`, `npm ls`, `cargo tree`, or equivalent) and list
   which versions actually differ between environments.
2. Check whether a lockfile exists, is committed, and is actually used by
   every install path (local setup, CI steps, the Docker build) -- `pip
   install`/`npm install` without a frozen/locked flag will silently
   re-resolve.
3. For native or binary-heavy dependencies, compare the exact artifact in
   the production image against what CI built with (base image tag, glibc,
   platform tag in the wheel or binary filename).
4. Reproduce against prod's exact state: install the deployed lockfile hash
   or image's resolved set into a local env and watch whether the bug
   appears.

## Fix

Make the resolved dependency set an explicit, committed, verifiable input
to every environment: commit a lockfile as part of the upgrade PR, and use
locked/frozen install commands (`--locked`, `--frozen`, `npm ci`,
`pip install --require-hashes`, etc.) in local setup, CI, and the Docker
build so nothing ever re-resolves. Where platform-specific artifacts
matter, build and test inside the same base image that ships to production
(a multi-stage Docker build that ends on the production image's base, and
CI running on that image), and record the exact resolved version plus
artifact in the upgrade PR so prod and CI are provably running the same
thing.

## Pitfalls

Adding "install succeeded locally" as a gate catches nothing, because the
bug is precisely that the environments resolved *differently*, not that
resolution failed. The check that matters is that the resolved versions are
identical across environments -- so verify lockfile hashes and resolved
sets, not install success, and never let "it works on my machine" substitute
for confirming CI and prod installed the same artifact.

## Verify

After the fix, confirm the lockfile hash of the deployment artifact and of
a fresh CI build are byte-identical to the committed lockfile. Then
reproduce the original bug by pointing a local environment at the exact
previously-deployed resolved set from production, apply the pinned upgrade,
and confirm the bug is gone from that same environment -- not just from a
machine that happened to resolve newer versions.