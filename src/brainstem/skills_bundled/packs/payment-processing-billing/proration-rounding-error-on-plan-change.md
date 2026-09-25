---
name: proration-rounding-error-on-plan-change
description: A customer who upgrades or downgrades their subscription mid-billing-cycle is charged or credited an amount that is off by a cent or more from the correct prorated value.
triggers: ["proration is wrong", "customer overcharged after upgrade", "prorated credit doesn't match", "plan change billed incorrectly", "proration off by a cent"]
permissions: ["READ"]
---

## Symptom
A customer changes plans partway through a billing period (upgrade,
downgrade, or seat-count change), and the resulting proration charge or
credit doesn't match what a manual calculation says it should be -- often
off by a small amount (a cent or a few cents), but sometimes off by a
whole day's or unit's worth of value, and often only noticeable in
aggregate when finance reconciles many accounts and finds the totals don't
tie out.

## Likely causes
1. **Off-by-one in the day-counting window** -- treating the change day
   as belonging to both the old and new plan (or neither), because the
   "days remaining" calculation uses an inclusive/exclusive boundary
   inconsistently (e.g. `(end_date - change_date).days` vs
   `(end_date - change_date).days + 1`).
2. **Floating-point arithmetic for money** -- computing `daily_rate =
   monthly_amount / days_in_month` as a float and multiplying by remaining
   days accumulates binary floating-point rounding error, especially
   visible when `days_in_month` doesn't divide evenly (28, 30, 31).
3. **Inconsistent rounding direction between the credit and the charge** --
   the unused-time credit on the old plan is rounded down while the new
   plan's prorated charge is rounded up (or each uses a different
   rounding mode entirely), so the two don't net out to the amount a
   customer would expect from "credit for unused old plan, charge for
   remaining new plan."
4. **Calendar-month billing periods of different lengths treated as a
   fixed constant** -- hardcoding 30 days as the period length for
   proration math produces a systematically wrong daily rate in 28-, 29-,
   and 31-day months.
5. **Timezone mismatch between when "now" is captured for the change and
   the billing period's stored boundaries** -- a change recorded in UTC
   compared against period boundaries stored in the customer's local time
   (or vice versa) can shift which day is counted as the change day.

## Diagnose
- Pull the actual stored values used in the calculation for the affected
  customer: old plan amount, new plan amount, billing period start/end,
  change timestamp, and the exact intermediate `days_remaining` /
  `daily_rate` values -- most proration bugs are visible once you print
  the intermediate numbers rather than just the final charged amount.
- Recompute the expected proration by hand using integer cents and exact
  day counts from the actual calendar (not an assumed 30-day month), and
  diff against what was actually charged/credited.
- Check whether the amounts in code are floats (`0.1 + 0.2` style
  representability issues) or a decimal/integer-cents type by grep'ing the
  proration function for the money types it operates on.
- Check if the discrepancy is consistent (always off by the same
  direction/amount) across multiple customers, which points to a rounding
  or off-by-one bug in the formula, versus inconsistent/random, which
  points to a timezone or boundary-detection race.

## Fix
Do all money math in integer minor units (cents) or a fixed-point decimal
type, never binary floats, so intermediate values don't accumulate
representable-precision error. Compute proration using explicit,
consistently-defined day boundaries: decide once whether the change day
belongs to the old plan or the new plan (a common convention: the customer
uses the old plan through end-of-day on the change date, the new plan
starts the next day) and apply that convention identically everywhere,
including in the "days remaining" and "days elapsed" halves of the
calculation so they sum to exactly the total period length. Compute the
unused-old-plan credit and the new-plan charge with the same rounding
function and the same rounding mode (e.g. round-half-even, applied last,
not at each intermediate step), and reconcile them into a single net
line item rather than two independently-rounded amounts that may not
cancel cleanly. Use the actual number of days in the specific billing
period (from real calendar date arithmetic) as the denominator, never a
hardcoded 30.

## Pitfalls
- "Fixing" the rounding by rounding intermediate values (e.g. rounding the
  daily rate before multiplying by days remaining) instead of only
  rounding the final result -- this reintroduces accumulated error just
  one step later and can make small accounts (low-dollar plans) visibly
  wrong even though the formula "looks" fixed.
- Assuming all billing periods are 30 days for simplicity -- this
  systematically overcharges customers changing plans in February and
  undercharges in 31-day months, and the error is consistent enough that
  customers comparing months will notice.
- Fixing proration for upgrades but not auditing downgrades (or vice
  versa) -- the credit-calculation path and the charge-calculation path
  are often separate code paths that drift independently after the first
  fix.

## Verify
Pick a real billing period (e.g. a 31-day month) and a plan change exactly
mid-period, compute the expected credit and charge by hand in integer
cents using the agreed day-boundary convention, then run the actual
proration function against the same inputs and assert the outputs match
to the cent -- repeat for a 28-day February period and a change on the
very first and very last day of a period to catch boundary-specific bugs.
