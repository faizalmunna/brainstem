---
name: major-version-upgrade-deferred-until-its-a-rewrite
description: A known major-version dependency upgrade keeps getting pushed to next quarter until the gap between current and latest is so large the upgrade now requires a near-rewrite.
triggers: ["we're 6 major versions behind", "nobody wants to touch the upgrade", "this dependency upgrade got way bigger than it should have been", "we kept putting off the framework upgrade"]
permissions: ["READ"]
---

## Symptom

A dependency (often a framework, ORM, or language runtime) sits several
major versions behind latest, and every time it comes up in planning
it's pushed out again. When someone finally attempts it, the diff touches
a large fraction of the codebase, several intermediate migration guides
have to be chained together, and the effort estimate balloons past
anything that would have been approved if proposed up front -- so it gets
deferred again, and the gap keeps growing.

## Likely causes

- **The upgrade has no owner and no deadline**, so it competes against
  every feature ticket that has both, and always loses -- there's no
  forcing function until something breaks (EOL, a security CVE, a new
  hire who can't use a modern feature).
- **Each individual version bump was skipped because "we'll batch them
  later,"** which seems efficient but actually compounds risk: N
  one-version upgrades each have a small, well-documented migration
  guide; one N-version upgrade has to manually reconstruct the union of
  every intermediate breaking change, often without a single coherent
  guide covering the whole span.
- **The team has no visibility into how far behind they are** -- nothing
  surfaces the version gap as a number anyone tracks, so it drifts
  silently instead of triggering a conversation at a threshold.
- **Past attempts failed loudly** (a broken deploy, a rushed rollback),
  which taught the team "upgrading this is dangerous" instead of
  "upgrading this in one big jump is dangerous," reinforcing deferral as
  the safe choice.

## Diagnose

1. Get the exact current and latest version, and count how many major
   versions/breaking-change boundaries separate them (check the
   package's changelog or release list, not just semver diff).
2. Pull up every intermediate major-version migration guide between
   current and latest and estimate whether they compose cleanly (do
   later guides assume earlier migrations are already done?) or contain
   contradictory intermediate steps.
3. Search the codebase for usage of any API the changelogs mark as
   removed or changed, and get a rough count of call sites affected --
   this is the number that should have been visible months ago.
4. Check whether the current version is still receiving security
   patches; an unsupported version turns this from a backlog item into
   an active risk with a clock on it.

## Fix

Treat "days since last dependency major-version bump" or "N major
versions behind latest" as a tracked metric with an agreed threshold
(e.g., "no core dependency more than one major version behind"), reviewed
on a fixed cadence (monthly/quarterly) rather than opportunistically.
When a metric crosses the threshold, the upgrade becomes a scheduled,
estimated, owned piece of work -- not a favor someone does when they have
spare time. For a dependency that's already far behind, don't attempt
the full jump in one PR: upgrade one major version at a time, running the
full test suite and a deploy/soak cycle between each step, so each step
is small, independently revertible, and uses the vendor's actual
migration guide for that specific version boundary instead of an ad hoc
reconstruction.

## Pitfalls

Don't "catch up" by jumping straight to latest and fixing whatever
breaks -- skipping the intermediate steps means you lose the
vendor-authored migration guidance for each boundary and end up
debugging several unrelated breaking changes simultaneously, unable to
tell which change caused which symptom.

## Verify

After establishing the policy, confirm it's actually enforced by
checking that the tracked "versions behind" metric for core dependencies
is visible somewhere the team looks regularly (dashboard, recurring
ticket, CI badge) and that at least one upgrade has been scheduled and
completed as a direct result of crossing the threshold, not as a
one-off.
