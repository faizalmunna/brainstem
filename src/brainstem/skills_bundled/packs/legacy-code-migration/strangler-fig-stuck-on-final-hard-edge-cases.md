---
name: strangler-fig-stuck-on-final-hard-edge-cases
description: A strangler-fig migration successfully routes most traffic to the new system but stalls indefinitely at partial completion because the last, hardest edge cases keep getting deprioritized.
triggers: ["strangler fig migration stuck", "migration stalled at 90 percent", "legacy system never fully decommissioned", "last edge cases blocking migration completion"]
permissions: ["READ"]
---

## Symptom

A strangler-fig migration (incrementally routing an increasing
percentage of traffic/functionality from an old system to a new one)
successfully reaches a high percentage of coverage relatively quickly,
then stalls there for a long time -- months or longer -- because the
remaining traffic represents the hardest, most complex edge cases, and
they keep losing priority to other work.

## Likely causes

- **The easy, high-volume cases were migrated first** (reasonably, since
  they deliver the most value fastest), but this means the remaining
  work is disproportionately the hardest cases relative to its share of
  actual traffic/usage, making its cost-to-value ratio look poor compared
  to other competing priorities.
- **The legacy system still fully works for the remaining edge cases**,
  so there's no urgent forcing function pushing the team to finish --
  unlike a broken system that demands attention, a partially-migrated
  system that's "good enough" can coast indefinitely.
- **The cost of keeping the legacy system running for just the remaining
  edge cases isn't visible/tracked as an ongoing cost** (the
  infrastructure, the on-call burden, the cognitive load of two systems),
  so the case for finishing doesn't compete well against more visible,
  immediate feature work.
- **The remaining edge cases individually seem small enough to defer
  "just one more sprint"** repeatedly, with no single decision point ever
  forcing a real prioritization conversation about actually finishing.

## Diagnose

1. Quantify the actual ongoing cost of maintaining the legacy system for
   just the remaining edge cases -- infrastructure cost, on-call
   incidents specifically tied to it, engineering time spent
   understanding/modifying it -- to make the "coasting" cost visible
   rather than abstract.
2. Characterize exactly what's different/harder about the remaining
   edge cases compared to what's already been migrated, to understand
   whether they're genuinely complex or just under-scoped/under-resourced.
3. Review how many planning cycles the remaining work has been deferred,
   and what specifically caused each deferral, to establish the pattern
   concretely rather than anecdotally.
4. Assess whether the remaining edge cases could be broken down further
   into smaller, individually completable pieces, rather than treated as
   one large remaining block.

## Fix

Make the ongoing cost of the dual-system state an explicit, tracked line
item (in planning, in cost reporting) so it competes visibly against
other priorities rather than being an invisible tax. Break the remaining
hard edge cases into the smallest independently-completable pieces
possible, so progress can continue incrementally rather than requiring
one large final push. Set an explicit target date for full legacy
decommissioning with organizational buy-in, treating it as a real
commitment (similar to how the initial migration likely had one) rather
than an open-ended "eventually."

## Pitfalls

Don't force the remaining hard edge cases through an artificially
compressed timeline just to hit a decommissioning date -- if they're
genuinely complex, rushing them risks the kind of quality/correctness
issues the migration was presumably being careful about for everything
else; balance urgency with the same care applied to earlier phases.
Also don't declare the migration "essentially done" and stop tracking
it once the easy majority is migrated -- that's exactly the framing that
lets the remaining piece stall indefinitely.

## Verify

Track the legacy system's actual remaining usage/traffic percentage over
time after implementing the fix and confirm it continues trending toward
zero rather than plateauing again. Confirm the legacy system is actually
decommissioned (not just "mostly unused but still running") by the
committed target, with the ongoing dual-maintenance cost genuinely
eliminated.
