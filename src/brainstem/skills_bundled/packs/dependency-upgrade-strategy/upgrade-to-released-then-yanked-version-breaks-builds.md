---
name: upgrade-to-released-then-yanked-version-breaks-builds
description: A dependency upgrade targets a version that was published and then retracted from the registry, so fresh installs fail or resolve differently while previously built environments keep working.
triggers: ["install failing because a package version was unpublished", "the version we upgraded to was yanked", "resolver reached a yanked version", "dependency we upgraded to no longer exists on the registry"]
permissions: ["READ"]
---

## Symptom

After an upgrade (or a lockfile refresh on an existing upgrade), installs
start failing or resolve to a different set of versions than the lockfile
records: a Docker build or CI restore that worked yesterday fails today
with an error such as "no matching version," "version does not exist," or a
registry 404. Machines and pipeline stages that *already have the package
installed or cached* keep working fine, which makes the failure appear
random. The referenced version was published, picked up, and then removed
or *yanked* from the registry -- either because it was a bad publish or a
compatibility problem was found after release -- so availability changed
after your manifest or lockfile was written.

## Likely causes

- **The version was retracted after the fact** (an npm unpublish or
  deprecate-with-yank, a package index yank, a deleted Git tag or source
  archive), so the reference in your lockfile points at something that no
  longer exists for fresh installs.
- **A loose constraint resolved to the version while it existed**, and a
  later install on any fresh environment -- a new developer machine, a
  cleared CI cache, a new container layer, a package restore -- can no
  longer resolve it, re-picking "whatever's newest" instead.
- **Caching splits the environment population:** some stages serve the
  package from local caches (venv, npm cache, Maven local, a warm Docker
  layer) while others must re-fetch and fail, so present-versus-failing is
  a function of who has cache rather than who has correct versions.
- **The upgrade was reviewed and tested while the version still existed**
  and merged after it was gone -- the PR diff was fine, but the version's
  availability moved between review and merge.

## Diagnose

1. Ask the registry whether the version still exists, rather than trusting
   the lockfile or a warm cache: `npm view <pkg>@<version>`, `pip index
   versions <pkg>`, or an HTTP request for the exact version's metadata.
2. Distinguish "never existed" (a typo or never-published version) from
   "existed and was retracted" (yanked, deprecated, or unpublished) -- the
   two have different causes and different fixes.
3. Determine each environment's cache state: identify exactly which
   pipeline stages install cold versus from a warm cache, to know which
   step will fail next and which are only passing by luck.
4. Check the package's version list and the maintainer's release channel
   for a replacement version, or a "do not use this build, use X instead"
   notice.

## Fix

On a retracted version, move to the nearest *actually available* version
that carries the feature or fix you wanted, and remove the reference to
the dead version in the same change -- leaving a dead reference in the
lockfile guarantees every future cold install reproduces the failure,
regardless of how many green builds pass in between from cache. Where the
package has a history of unstable releases, add explicit version-range
bounds that exclude the yanked versions, and consider fully pinning or
vendoring the dependency if retractions keep happening. In CI, prefer
frozen/locked installs so a cold build fails loudly at install time (naming
the unreachable version) instead of silently resolving an unintended
compatible version that no one reviewed.

## Pitfalls

Don't "fix" a yanked version by loosening the constraint so resolution
skips around it without checking *why* it was retracted. If the version was
yanked because it was broken -- a bad publish, a vulnerability, an
incompatibility -- silently landing on "whatever's newest" can install a
version you don't control, or re-introduce the very problem that caused the
yank through a deprecation that keeps the broken version published.

## Verify

After pinning the replacement version, run a fully cold, clean install
(registry caches cleared, fresh container start) and confirm it
deterministically succeeds or fails with the intended replacement version
in the resolved set. Confirm the resolved set no longer references any
yanked or unavailable version per the registry's own metadata, and that a
repeat cold install in CI yields the same result on an empty cache.