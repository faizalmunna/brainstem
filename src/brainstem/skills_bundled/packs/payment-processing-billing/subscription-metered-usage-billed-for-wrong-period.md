---
name: subscription-metered-usage-billed-for-wrong-period
description: A usage-based or metered subscription invoice includes usage events from outside the intended billing period, double-billing or omitting consumption near a period boundary.
triggers: ["usage billed twice at period boundary", "metered invoice missing last day of usage", "usage-based billing off by one period", "overage charged for wrong month"]
permissions: ["READ"]
---

## Symptom
A metered/usage-based subscription (API calls, seats-days, compute
minutes, etc.) generates an invoice where the usage total doesn't match a
manual sum of the raw usage events for that customer's actual billing
period -- usage recorded right at the start or end of a period is either
counted in both the current and adjacent invoice, or counted in neither,
and it's most visible for customers whose usage pattern spikes right
around their renewal date.

## Likely causes
1. **Usage events are aggregated using an inconsistent boundary
   convention relative to the period start/end timestamps** -- e.g. usage
   query uses `>= period_start AND <= period_end` (inclusive on both ends)
   while the period-generation logic defines `period_end` as equal to the
   *next* period's `period_start`, causing the boundary instant's usage to
   be double-counted across two invoices.
2. **Usage is recorded with the event's ingestion/processing timestamp
   instead of the timestamp of when the usage actually occurred**, so
   usage that happened just before a period boundary but was processed
   (due to batching, queue delay, or clock skew between services) just
   after the boundary gets attributed to the wrong period.
3. **The billing period boundaries themselves shift** when a subscription
   is paused, upgraded, or has its renewal date changed mid-cycle (see
   `proration-rounding-error-on-plan-change`), but the usage-aggregation
   query still uses the *original* period boundaries cached somewhere,
   creating a mismatch between what period the invoice claims to cover and
   what period the usage query actually pulled from.
4. **Usage aggregation runs before all usage for the period has actually
   landed** -- e.g. the invoice is generated at exactly period-end, but
   usage-reporting events from the last few minutes/hours of that period
   are still in flight (async ingestion pipeline lag), so the invoice
   undercounts and there's no later reconciliation/adjustment step to
   catch the late-arriving events.

## Diagnose
- Pick a customer's invoice near a period boundary and independently sum
  the raw usage events (from the source of truth, e.g. an events table or
  metering pipeline) using an explicit, unambiguous boundary definition
  you choose yourself, then compare against the invoiced amount -- the
  direction of the discrepancy (over vs under) narrows down which cause
  applies.
- Check the exact SQL/query boundary conditions used by the invoice-
  generation job (inclusive vs exclusive on each end) and check them
  against the values actually used to define `period_start`/`period_end`
  when periods are created, to catch the off-by-boundary mismatch
  directly in code.
- Check what timestamp field usage events are aggregated by -- event
  occurrence time vs ingestion/processing time -- and check for
  measurable lag between the two in the ingestion pipeline (queue depth,
  processing delay metrics).
- Check whether the invoice-generation job runs any grace delay after
  period-end before aggregating (to let in-flight usage settle), or fires
  immediately at the boundary instant.

## Fix
Define billing period boundaries with one explicit, consistently-applied
convention across every piece of code that touches them (e.g.
`[period_start, period_end)` -- inclusive start, exclusive end) and use
that same convention both when periods are created and when usage is
aggregated for invoicing, so there is no instant that belongs to two
periods or to none. Aggregate usage by the event's actual occurrence
timestamp, not its ingestion timestamp, and if periods can shift (pause,
upgrade, renewal-date change), re-derive the usage query's boundaries from
the *current* authoritative period record at invoice-generation time
rather than from a value cached earlier. Add a short, deliberate delay (or
a late-usage reconciliation/adjustment invoice) between period-end and
invoice generation to absorb realistic ingestion pipeline lag, and treat
usage events that still arrive after that window as an explicit
correction on a subsequent invoice rather than silently dropping them.

## Pitfalls
- Fixing the boundary convention in the invoicing query but not in the
  usage-metering dashboard/API customers see -- if the customer-facing
  usage view uses a different boundary than what's actually billed,
  support disputes continue even after the billing math itself is
  correct, because the customer's own math (based on the dashboard) still
  disagrees.
- Adding a delay before invoice generation without communicating it
  anywhere, so on-call/support assumes an invoice should be ready
  immediately at period-end and treats the intentional delay as an
  outage.
- Handling late-arriving usage by silently mutating an already-sent
  invoice instead of issuing a visible adjustment -- customers and
  accounting systems both need a paper trail for why an amount changed
  after the fact.

## Verify
Generate synthetic usage events with timestamps deliberately placed one
second before and one second after a period boundary, run the actual
invoice-generation job for both the ending and the new period, and confirm
each event appears in exactly one invoice's usage total, matching the
chosen boundary convention exactly.
