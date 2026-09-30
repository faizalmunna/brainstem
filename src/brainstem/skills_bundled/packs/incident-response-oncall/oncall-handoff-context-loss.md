---
name: oncall-handoff-context-loss
description: On-call shift handoff loses context on an ongoing issue because there is no structured process, so the incoming engineer starts cold.
triggers: ["on-call handoff", "new on-call engineer has no context", "shift change lost incident context", "handoff between on-call shifts", "picked up a ticket with no background"]
permissions: ["READ"]
---

## Symptom
An issue is being investigated (or a known-degraded state is being
tolerated) when an on-call shift ends. The outgoing engineer goes
offline, and the incoming engineer either doesn't know the issue exists
until a page fires, or knows something is "going on" but has to
reconstruct what's been tried, what's ruled out, and what the current
working theory is from scratch -- often by scrolling through a long chat
thread or re-running diagnostics the outgoing engineer already ran.
Response to the ongoing issue visibly slows down right at the shift
boundary.

## Likely causes
- **Handoff is informal/verbal-only ("I'll ping you if anything's up")**
  with no written artifact, so context that exists only in the outgoing
  engineer's head is unavailable the moment they log off or are
  unreachable.
- **There's a handoff process but it's a ritual, not a real transfer** --
  a "handoff" message that just says "no major issues" without checking
  for in-progress lower-severity investigations, known flaky alerts, or
  scheduled risky changes that could bite the next shift.
- **The information exists but is scattered** across a chat thread, a
  monitoring dashboard, and one person's memory, with no single place the
  incoming engineer can check before their shift starts.
- **No overlap window between shifts** -- the outgoing engineer is
  already off rotation by the time the incoming engineer would have
  questions, so ambiguities can't be resolved synchronously.
- **Organizational assumption that "nothing is on fire" means nothing
  needs to be said**, missing that a contained-but-unresolved issue, a
  suppressed alert, or a risky change in flight all need explicit
  transfer even without an active page.

## Diagnose
1. Check whether a written handoff artifact exists at all (a doc,
   channel message, ticket) versus purely verbal/ad hoc -- absence is the
   most common root cause.
2. If one exists, check its content against a real ongoing situation from
   the last few shifts: did it actually mention the in-progress
   investigation, or only cover pages that fired during that exact shift?
3. Ask the incoming engineer, after a slow response to a known-ongoing
   issue, what they knew at shift start and when they learned about the
   issue -- if they learned from a fresh page rather than the handoff,
   the handoff failed to transfer known risk.
4. Check for an overlap window: is there any point where outgoing and
   incoming on-call are both online, or does the transfer happen
   instantaneously with no chance to ask a clarifying question?

## Fix
Require a structured, written handoff for every shift change, not just
when something is actively on fire: a short template covering (1) any
open incidents or investigations and current working theory, (2) any
known-degraded or suppressed alerts and why, (3) any risky changes
recently deployed or scheduled during the next shift, (4) anything
non-obvious about current system state a fresh responder wouldn't know.
Post it somewhere durable and searchable (not just a message that scrolls
away), and require the incoming engineer to actively acknowledge reading
it, not just receive it silently. Build in a short overlap window (even
15-30 minutes) where both engineers are reachable so ambiguous items in
the handoff can be clarified synchronously instead of the incoming
engineer guessing. This works because it converts context that
previously lived only in one person's head into a durable artifact plus
a real synchronous check, which is what survives the actual transfer
moment.

## Pitfalls
Don't let the handoff template become a rubber-stamped "all clear" filled
in from habit without the outgoing engineer actually checking dashboards
first -- a template followed mechanically without real review is no
better than no template. Also don't make the handoff so long/bureaucratic
that people skip writing it under time pressure at the end of a rough
shift; keep it to what's actually actionable for the next person, not a
full narrative of everything that happened.

## Verify
After introducing the structured handoff, check the next few shift
transitions for whether an ongoing lower-severity issue (if one exists)
appears explicitly in the handoff artifact before the shift ends. Time-to
-acknowledge on any issue that was already known at shift start should
measurably improve versus historical shift-boundary incidents where the
information wasn't transferred.
