---
name: status-page-stale-during-incident
description: The customer-facing status page or incident communication is inaccurate or stale relative to the internal understanding of impact during an incident.
triggers: ["status page is wrong", "customers are more affected than the status page says", "status page not updated during outage", "customer communication out of sync with incident", "support is getting complaints the status page doesn't match"]
permissions: ["READ"]
---

## Symptom
While an incident is actively being worked, the public status page still
shows "investigating" or an earlier, narrower description of impact,
while internally the team already knows the scope is broader (more
services affected, a workaround no longer works, an ETA has slipped) or
already knows it's resolved. Customers and support teams are working off
stale information, support tickets pile up asking questions the internal
team already has answers to, and trust in the status page erodes because
people learn it lags reality.

## Likely causes
- **Updating the status page is a manual, low-priority side task**
  assigned to whoever's free, competing for attention against actually
  fixing the issue, so it's the first thing skipped under pressure.
- **No one owns customer communication as a distinct responsibility
  separate from technical response** -- the same people fixing the issue
  are also expected to remember to update the status page, and the fix
  always wins the attention contest.
- **The status page update requires manually translating internal
  technical detail into customer-safe language**, which takes enough
  effort/judgment that it gets deferred ("we'll write a proper update
  once we know more") past the point where *any* update would have been
  better than silence.
- **There's no cadence/SLA for status updates** -- without a rule like
  "update at least every 30 minutes even if there's no news," updates
  only happen when someone remembers, which is irregular and biased
  toward being forgotten during the most chaotic incidents.
- **Support/customer-facing teams aren't in the incident channel**, so
  the gap between internal knowledge and external communication is
  invisible to the engineers who have the current information.

## Diagnose
1. Compare the status page's update timestamps and content against the
   internal incident timeline (chat log, incident ticket) for the same
   window -- measure the actual lag between internal knowledge and
   external communication at each point impact changed.
2. Check whether a specific person was assigned the communication role
   for this incident, or whether it was left implicit/nobody's job.
3. Check support ticket volume/content during the incident for questions
   that the status page's staleness directly caused (customers asking
   about impact the internal team already knew about but hadn't
   published).
4. Check whether there's a defined update cadence at all, and if so,
   whether it was actually followed for this incident (compare time
   between consecutive status page updates against the stated SLA).

## Fix
Assign a dedicated communications role for any incident above a defined
severity threshold, separate from the people actively fixing the
technical issue -- their job is specifically to keep the status page and
other external channels current, not to debug. Set an explicit update
cadence (e.g. "an update at least every 30 minutes even if it just says
'still investigating, no new information'") so silence is never the
default while an incident is open, and pre-approve simple, honest
boilerplate for "no update yet" so the comms owner doesn't need to craft
new prose every cycle under pressure. Give the comms owner a live feed
into the incident channel (or a direct line to the IC) so they're
translating current internal understanding, not working from whatever
was true 20 minutes ago. Loop in support/customer-facing teams directly
into the incident's communication updates so they're not learning impact
scope secondhand from confused customers.

## Pitfalls
Don't let the desire for a polished, fully-accurate update become an
excuse to delay any update -- a slightly imprecise "we're aware of
degraded performance and investigating" published promptly is better
than a precise paragraph published 40 minutes late. Also don't have the
IC or lead engineer try to own communications themselves "since they
know the most" -- that's exactly the attention contest that causes
staleness; the accuracy value of them writing it doesn't outweigh the
cost of them not fixing the issue while writing it.

## Verify
For the next incident above the severity threshold, measure the time
between an internal understanding change (scope widened, ETA slipped,
resolved) and the corresponding status page update -- it should stay
within the defined cadence SLA. Also check support ticket volume
during/after the incident for a reduction in "is anyone looking at this"
style tickets, which indicates customers are getting current information
without needing to ask.
