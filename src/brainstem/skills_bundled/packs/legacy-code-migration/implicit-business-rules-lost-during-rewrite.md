---
name: implicit-business-rules-lost-during-rewrite
description: A rewritten module silently drops or subtly changes an undocumented business rule that only existed as implicit logic in the legacy code, because nobody extracted and verified it before reimplementing.
triggers: ["rewrite lost a business rule", "legacy behavior not preserved in rewrite", "undocumented edge case missing after migration", "rewrite changed behavior nobody knew about"]
permissions: ["READ"]
---

## Symptom

After a legacy module is rewritten and deployed, a specific business
behavior that used to work correctly stops working (or works
differently) -- investigation reveals the legacy code encoded a specific
business rule that was never documented anywhere, existed only as
implicit logic buried in the old implementation, and wasn't carried over
because nobody knew it needed to be.

## Likely causes

- **The rewrite was based on documentation, requirements, or a general
  understanding of "what the system does"** rather than a careful line-
  by-line audit of the actual legacy implementation, so any behavior
  that was never documented (because it was added ad hoc, or because the
  original context was lost) had no chance of being noticed and
  preserved.
- **The specific rule only applies to a rare edge case** that doesn't
  show up in typical testing or in a reasonably-sized sample of
  production traffic, so its absence from the rewrite went unnoticed
  until that specific rare case actually occurred in production.
- **The original author(s) of the legacy behavior are no longer
  available** (left the company, moved teams) to explain the reasoning
  behind a specific piece of logic, so even if it was noticed during the
  rewrite, its purpose/necessity wasn't understood and it may have been
  judged (incorrectly) as safe to drop.
- **No characterization tests existed to pin down the legacy behavior
  before the rewrite began** (see this pack's characterization-testing
  skill), so there was no systematic mechanism forcing every observed
  behavior to be explicitly accounted for in the new implementation.

## Diagnose

1. For the specific lost/changed behavior, trace back to the exact
   legacy code path that implemented it, and understand precisely what
   condition triggers it and what it does.
2. Check whether the rule was ever documented anywhere (comments, old
   tickets, commit messages, design docs) to understand whether it was
   truly undocumented or simply missed during the rewrite's research
   phase.
3. Check production logs/data from before the rewrite for how often this
   specific rule actually fired, to understand why it wasn't caught by
   whatever testing/validation was done during the migration.
4. Search for other similar implicit rules nearby in the same legacy
   module, since a rewrite that missed one undocumented rule has likely
   missed others that haven't surfaced yet.

## Fix

Reimplement the specific missing/changed behavior in the new system,
now explicitly documented (in code comments, in a test, in design docs)
so its existence and reasoning are preserved for the future, unlike its
original undocumented state. More broadly, for any remaining
unmigrated or recently-migrated legacy modules, run the legacy and new
implementations in parallel against real production traffic (a
shadow/dual-run comparison) to surface behavioral differences
systematically, rather than waiting for them to manifest as user-visible
bugs one at a time.

## Pitfalls

Don't assume a rediscovered "lost" business rule should always be
restored exactly as it was -- some implicit legacy behavior is
accidental (a bug that became relied upon) rather than intentional;
investigate with the same care whether the discovered rule should be
preserved, fixed, or deliberately removed, ideally with input from
whoever owns the business logic rather than a unilateral engineering
decision.

## Verify

After reimplementing the specific behavior, confirm it now handles the
originally-triggering condition correctly, and add a test that
explicitly encodes it so a future refactor can't silently drop it again.
Run a broader shadow-comparison between old and new implementations over
a representative traffic sample to check for any other undiscovered
behavioral differences before considering the migration fully complete.
