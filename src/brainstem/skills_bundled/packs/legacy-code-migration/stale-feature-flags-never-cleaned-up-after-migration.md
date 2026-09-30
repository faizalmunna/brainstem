---
name: stale-feature-flags-never-cleaned-up-after-migration
description: Feature flags used to gate a completed migration are never removed afterward, accumulating as permanent complexity and creating confusion about which code path is actually active.
triggers: ["migration feature flags never removed", "old flag still in codebase after migration done", "stale flag confusing which path is active", "feature flag cleanup after rollout"]
permissions: ["READ"]
---

## Symptom

Long after a migration has fully completed and the old system/code path
has been retired, the feature flag(s) originally used to control the
gradual rollout are still present in the codebase -- still checked in
conditionals, still configured in a flag management system -- even
though they've been permanently set to the same value for a long time
and the "off" branch they gate is effectively dead code. This distinct
migration-specific pattern is a special case of general flag hygiene:
here the flag's entire purpose (gating a one-time migration) has been
fully served, unlike a flag meant for ongoing configuration.

## Likely causes

- **Removing a feature flag was never explicitly assigned as a task
  with an owner and a deadline** -- it was implicitly understood as
  "something to clean up eventually" once the migration finished, but
  "eventually" never got prioritized against other work once the
  migration's visible, high-priority phase was done.
- **The flag's "off" branch (the old code path) still exists and looks
  functional**, so there's no forcing pressure to remove it -- unlike a
  broken or obviously dead code path, it doesn't visibly demand
  attention.
- **Removing the flag requires touching code that's perceived as risky
  to modify** (the exact code the migration was originally cautious
  about), so the same risk-aversion that justified using a flag in the
  first place discourages removing it afterward.
- **Multiple flags accumulate across several migrations over time**, and
  without a systematic process to track and clean each one up after its
  purpose is served, they pile up as a general category of technical
  debt that no single migration's completion criteria ever explicitly
  included.

## Diagnose

1. Inventory all feature flags in the codebase/flag management system
   and check their current values and how long they've been set to
   that value without changing, which is a strong signal for flags that
   have finished serving their original purpose.
2. For each long-static migration-related flag, confirm the "off"
   (or "on," whichever leads to the old path) branch is genuinely dead --
   verify via traffic/usage data that it's never actually exercised in
   production.
3. Check whether flag removal was ever included in the original
   migration's definition of "done," or whether it was left implicit.
4. Assess the actual risk of removing each specific flag -- is the
   surrounding code itself risky to touch, or is the flag removal itself
   low-risk (a simple conditional deletion) once confirmed dead?

## Fix

Make flag cleanup an explicit, tracked part of any migration's
completion criteria from the start (not an afterthought), including an
owner and a target date for removal once the migration is confirmed
stable. For already-accumulated stale flags, treat cleanup as its own
small, scheduled project -- confirm each flag's dead branch via
production data, remove the flag and the dead code path, and verify
nothing regresses. Where a flag management system supports it, use
automated staleness detection (flags unchanged for N months) to
surface cleanup candidates proactively rather than relying on someone
remembering.

## Pitfalls

Don't remove a long-static flag without first confirming its "dead"
branch is genuinely unused -- some flags gate genuinely rare but
legitimate scenarios (a specific customer segment, an infrequent
operational mode) that could look dead in a short observation window but
aren't; check actual usage data over a representative period, not just a
quick look.

## Verify

After removing a stale flag and its dead code path, confirm the
application behaves identically to before (since the flag was already
statically set, behavior shouldn't change) via existing tests and a
production smoke check. Confirm the flag no longer appears in the flag
management system or codebase, and repeat the cleanup process
periodically as new migrations complete.
