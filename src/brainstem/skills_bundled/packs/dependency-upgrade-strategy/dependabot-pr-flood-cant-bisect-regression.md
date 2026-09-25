---
name: dependabot-pr-flood-cant-bisect-regression
description: A flood of automated dependency-bump pull requests are merged close together, a regression shows up later, and no single landed commit can be isolated as its cause.
triggers: ["dependabot merged everything and now something broke", "which dependency bump caused this regression", "can't bisect because every bump shipped together", "dozens of dependency PRs merged at once"]
permissions: ["READ"]
---

## Symptom

An automated tool (Dependabot, Renovate, a bot-driven `cargo update`/
`uv.lock` refresh) has been opening a steady stream of minor and patch
dependency bumps, and many of them get merged close together -- auto-merge
on green, a batch "merge all" session, or a backfill of months of
accumulated PRs. Later a regression appears: wrong behavior, a crash, a
performance cliff. The regression is real but no single landed diff shows
it, and `git bisect` fails or returns a misleading result because the
breaking change rides inside a dependency that changed across many of the
merged PRs at once.

## Likely causes

- **Auto-merge on green lets functionally separate bumps coalesce into an
  unbisectable batch.** Each PR passed CI in isolation, but the set never
  ran together, and the assumption that "one PR equals one behavior
  change" quietly stops holding once the batch ships as a unit.
- **The regression is an interaction between two bumps, each harmless
  alone.** Bump A changes a default; bump B starts exercising it. A
  commit-level bisect cannot find the commit where behavior changed,
  because behavior only changed when both were present.
- **The regression is inside the dependency's own code, which bisects
  differently.** The commit that "introduced" it is a lockfile refresh
  containing hundreds of version changes at once, none of which is itself
  a causal diff -- so bisecting app commits lands on a commit that is
  nothing but an inventory change.
- **The flood is itself the symptom of a policy gap:** no cap on how many
  bumps can merge per day, no grouping of bumps that touch the same
  dependency, no owner reading each diff.

## Diagnose

1. List the dependency version delta across the merged window by diffing
   the lockfile/manifest changes over the regression window, not just the
   app-source commits.
2. Check whether the bisect unit matches reality: `git bisect` over app
   commits is only meaningful if the breaking change landed as one app
   commit; per-commit, extract "which dependency's version changed" and
   diff that list against the regression window.
3. For a suspected pair, pin each involved dependency back to its
   pre-bump version one at a time and re-run the failing path -- a
   two-variable experiment that surfaces interaction bugs a commit bisect
   structurally cannot.
4. Look for any bumped version whose changelog between old and new
   mentions the failing behavior, even indirectly (a changed default, a
   replaced algorithm, an altered data format).

## Fix

Turn the "one bump equals one risk unit" assumption back on by capping
how many dependency bumps can be merged at once and by grouping bumps
that affect the same dependency or the same area of code into a single PR
(both Dependabot and Renovate support group config; the default is one PR
per dependency, which is exactly what produces the flood). When backfilling
many accumulated bumps, land them one at a time with a short soak, or at
minimum record the per-dependency version delta across the batch so a
later regression starts from a short suspect list. Keep a "known-good"
lockfile or reference commit representing the pre-batch state so the whole
batch is revertible as a unit if the regression only appears after it.

## Pitfalls

Don't assume `git bisect` will "just work" because it's reliable on
ordinary commits -- here the failing unit may not be a commit at all but a
*combination* of versions that exists in exactly one lockfile state. A
bisect that reports "no buggy commit" is a result, not a dead end: treat
it as evidence the cause is a dependency interaction and pivot to version
pin-back experiments instead of trusting the bisect's silence.

## Verify

Make a regression in a bumped area rapidly attributable: reproduce the
failure, then confirm that pinning a dependency from the recorded
per-dependency version delta back to its prior version makes the failing
case pass while everything else stays current. Confirm the merged PR
history now shows bumps grouped/batched such that no window contains more
unrelated dependency changes than a human can review at once.