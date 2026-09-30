---
name: reserved-commitment-underutilized-or-mismatched
description: A cloud provider's reserved instance or savings plan commitment goes underutilized because actual usage shifted away from the instance types or regions the commitment was made for.
triggers: ["reserved instances not fully utilized", "savings plan coverage low", "committed use discount wasted", "reserved capacity mismatch actual usage"]
permissions: ["READ"]
---

## Symptom

A cost report shows that a reserved instance (RI), savings plan, or
committed-use discount purchased to reduce compute costs isn't providing
its expected discount coverage -- actual pay-as-you-go charges continue
alongside the commitment, or the commitment's utilization percentage is
noticeably below 100%, meaning money was effectively pre-paid for
capacity that isn't being fully used.

## Likely causes

- **Actual instance usage shifted to a different instance family, size,
  or region than what the reservation was scoped to**, after an
  architecture change, a migration, or a rightsizing effort (see the
  overprovisioning skill in this pack) that wasn't coordinated with
  existing reservation commitments.
- **The reservation was purchased based on a point-in-time usage
  snapshot** that didn't account for planned or since-occurred changes in
  workload (a service decommissioned, a migration to a different compute
  model like serverless), leaving the commitment stranded against usage
  that no longer exists.
- **Reservations were purchased with insufficient flexibility** (zonal
  scope instead of regional, a specific instance size instead of a
  size-flexible family) relative to how usage patterns actually vary or
  evolve, making even small legitimate usage shifts fall outside the
  reservation's coverage.
- **No one owns tracking reservation utilization on an ongoing basis**,
  so a reservation purchased with good utilization initially can drift
  into poor utilization as usage evolves, with nobody positioned to
  notice or act on it.

## Diagnose

1. Pull the cloud provider's reservation/commitment utilization report
   and identify specifically which reservations have utilization below
   an acceptable threshold (this data is typically available directly
   from the provider's cost management tools).
2. For underutilized reservations, compare their scoped instance family/
   size/region against current actual usage patterns to identify the
   specific mismatch.
3. Check whether the underutilization is due to a permanent shift
   (an architecture change that isn't reverting) versus a temporary dip
   (an expected seasonal low) before deciding on a remediation approach.
4. Check whether reservations were purchased with size/region flexibility
   options that could already accommodate the actual current usage but
   simply weren't configured to do so.

## Fix

For reservations with size-flexibility options available, ensure that
flexibility is actually enabled/configured to automatically apply
across the covered instance family regardless of exact size. Where a
permanent usage shift has occurred, work through the cloud provider's
reservation modification/exchange/marketplace mechanisms (many providers
allow exchanging or reselling underutilized reservations) rather than
letting them go fully to waste for their remaining term. Going forward,
prefer more flexible commitment types (broader savings plans over
narrowly-scoped instance reservations) where the discount tradeoff is
acceptable, specifically to reduce future stranding risk from usage
pattern changes.

## Pitfalls

Don't purchase large, long-term reservations based on a single point-in-
time usage snapshot without considering how usage is likely to evolve
over the commitment period -- align commitment term length and
flexibility with actual confidence in usage stability, and prefer
shorter terms or more flexible commitment types when usage patterns are
still evolving or uncertain. Also don't ignore a known underutilized
reservation simply because "it's already paid for" -- actively pursuing
an exchange or modification can still recover value for the remaining
term.

## Verify

After applying flexibility settings or exchanging underutilized
reservations, monitor utilization percentage over the following billing
cycles and confirm it improves toward full coverage. Establish an
ongoing (e.g. monthly) reservation utilization review so future
underutilization is caught and addressed promptly rather than
accumulating unnoticed.
