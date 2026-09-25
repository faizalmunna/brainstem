---
name: big-bang-rewrite-stalls-abandoned-midway
description: A full rewrite of a legacy system stalls or is abandoned partway through because its scope was too large to deliver incrementally, leaving two half-maintained systems running.
triggers: ["rewrite stalled halfway", "big bang rewrite abandoned", "legacy rewrite never finished", "maintaining old and new system both"]
permissions: ["READ"]
---

## Symptom

A project to fully rewrite a legacy system loses momentum months or
years in -- feature parity was never reached, the team is now
maintaining both the old and new systems simultaneously (doubling
maintenance burden instead of reducing it), and there's no clear path
or timeline to actually finishing and decommissioning the old system.

## Likely causes

- **The rewrite's scope was defined as "replace everything" up front**,
  with no incremental delivery milestones, so there was no point during
  the project where partial progress produced standalone value -- only
  full completion would have paid off, making it easy for priorities to
  shift away before that point was reached.
- **The legacy system kept receiving feature changes and bug fixes
  during the rewrite**, so the rewrite team was chasing a moving target,
  perpetually behind because the old system never stopped evolving while
  the new one was being built to replace a now-outdated snapshot of it.
- **Undocumented edge cases and business rules embedded only in the
  legacy code** kept surfacing during the rewrite, each one requiring
  investigation and rework, extending the timeline well beyond the
  original estimate that assumed the legacy behavior was well understood.
- **No executive/organizational commitment protected the rewrite's
  priority** against competing feature work, so as soon as a
  higher-visibility priority came up, engineers were pulled off the
  rewrite, and it was never fully resourced again.

## Diagnose

1. Assess actual current state: what fraction of legacy functionality is
   genuinely covered by the new system, and what's the realistic
   remaining scope, not the original optimistic estimate.
2. Check whether the legacy system has continued to change since the
   rewrite started, and by how much, to quantify how much of a moving
   target it's been.
3. Interview the team for the specific blockers that caused momentum to
   stall -- resourcing, unexpected complexity, unclear ownership -- to
   distinguish a scoping problem from a prioritization problem.
4. Calculate the actual current cost of maintaining both systems
   (engineering time, operational complexity, bug surface) to make the
   cost of the stalled state concrete rather than abstract.

## Fix

Restructure the remaining migration around a strangler-fig approach --
incrementally route specific, bounded pieces of functionality from the
legacy system to the new one, with each increment shipping real,
standalone value and allowing partial legacy decommissioning along the
way, rather than requiring full completion before any of the old system
can be retired. Freeze new feature development on the legacy system for
the specific areas being actively migrated (not necessarily the whole
system) so the target stops moving in that scope. Get explicit, durable
organizational commitment (a protected allocation of engineering time)
for the remaining migration work, informed by the realistic scope
assessment rather than the original estimate.

## Pitfalls

Don't restart the rewrite from scratch with a "this time we'll do it
right" mentality -- that discards real progress already made and risks
repeating the same big-bang scoping mistake; incrementalize the
*existing* effort rather than abandoning it for a fresh attempt. Also
don't freeze the legacy system's evolution entirely if parts of it
genuinely need continued maintenance/features outside the migration's
current scope -- freeze only the specific areas actively being migrated.

## Verify

Confirm the first incrementally-migrated piece of functionality actually
ships and allows a corresponding piece of the legacy system to be
retired or marked deprecated, proving the new strangler-fig approach
produces real, bounded progress rather than repeating the all-or-nothing
pattern. Track migration progress as a shrinking legacy surface area
over time, not just "rewrite % complete."
