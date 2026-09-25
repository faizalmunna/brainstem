---
name: upgrade-merged-on-green-tests-without-reading-changelog
description: A dependency bump is approved and merged purely because CI stayed green, missing a documented breaking behavior change the existing tests never exercised.
triggers: ["tests passed but prod broke after the upgrade", "the changelog mentioned this and we missed it", "silent breaking change in dependency upgrade", "we didn't read the migration guide before merging"]
permissions: ["READ"]
---

## Symptom

A dependency version bump PR shows all green checks and gets merged on
that basis alone. Some time later -- sometimes immediately, sometimes
only under a specific input or load condition -- production exhibits a
behavior change traceable to that dependency: a changed default, a
different error type, a subtly different rounding/ordering/timeout
behavior. The changelog or migration guide for that release documented
the change explicitly; nobody read it before merging.

## Likely causes

- **The upgrade was treated as routine because it was "just a patch/minor
  bump" or came from an automated bot**, so it got the same low-scrutiny
  review as a typo fix, when the actual diff in the dependency's own
  behavior was much larger than the version-number jump suggested.
- **The existing test suite tests the codebase's own logic, not the
  dependency's contract** -- it was never written to pin down the
  specific default values, edge-case behaviors, or error semantics that
  the new version changed, so it has no way to catch a change it was
  never asserting on in the first place.
- **The changelog exists but is long, unstructured, or split across
  several intermediate releases**, making "just read it" a real time
  cost that reviewers under deadline pressure skip, especially when the
  diff itself looks small.
- **The breaking change only manifests under production-scale
  conditions** (real traffic patterns, real data shapes, concurrency)
  that local/CI tests don't replicate, so even a careful manual test pass
  wouldn't have caught it -- only reading the documented change would
  have.

## Diagnose

1. Pull the exact changelog / release notes / migration guide for the
   specific version range being bumped (not just the latest release --
   every intermediate version in the range if it's not a single-version
   bump).
2. Search the changelog text for the words "breaking", "changed
   default", "deprecated", "removed", "behavior change" -- these are
   almost always called out explicitly by maintainers who know they're
   dangerous.
3. Cross-reference each flagged change against actual usage in the
   codebase (grep for the affected API, config key, or default-dependent
   code path) to determine real exposure, not just theoretical risk.
4. For any flagged change touching code with no direct test coverage,
   treat that as a gap to close before merging, not after.

## Fix

Make changelog/migration-guide review a required, visible step in the
PR itself, not an assumed-but-unverified human habit: the PR description
should name the specific version range, link the changelog, and list any
breaking changes considered relevant (even "reviewed, none applicable"
is a stronger signal than silence). For dependencies central enough to
matter, write characterization tests that pin down the specific behavior
your code relies on (a default value, an error type, a formatting rule)
so a future upgrade that changes it fails loudly in CI instead of
silently in production -- this converts "read the changelog every time"
into "the test suite catches it even if someone forgets."

## Pitfalls

Don't treat "the diff is small" as a proxy for "the risk is small" --
some of the most damaging breaking changes are one-line default changes
(a timeout, a serialization format, a null-handling rule) that produce a
minimal code diff but a large behavioral one, precisely because nothing
in the calling code needed to change for the new behavior to take
effect.

## Verify

Confirm the fix worked by checking that the next dependency upgrade PR
in the repo actually contains a changelog summary or link in its
description before merge, and that at least one previously-unpinned
behavior (a default, an error type) now has an explicit test asserting
it, so a future version bump that changes it fails CI instead of
shipping silently.
