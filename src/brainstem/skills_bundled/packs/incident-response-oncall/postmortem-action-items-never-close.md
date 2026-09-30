---
name: postmortem-action-items-never-close
description: Postmortem action items get written down after every incident but rarely get completed, and the same category of incident recurs months later.
triggers: ["postmortem action items never get done", "same incident happened again", "follow-up items from postmortem are stale", "action item backlog incident review", "we keep having the same outage"]
permissions: ["READ"]
---

## Symptom
Every postmortem ends with a tidy list of action items -- "add
monitoring for X," "add a runbook for Y," "fix the underlying race
condition in Z" -- and the document gets approved and filed. Six months
later, an incident review turns up the same or a closely related failure,
and someone finds the old postmortem with the relevant action item still
marked "open" or "in progress," untouched since it was created.

## Likely causes
- **Action items are assigned to a team or "owner: TBD" rather than a
  named individual with a due date**, so nobody experiences it as their
  responsibility and it silently loses every prioritization fight against
  dated feature work.
- **Action items live only inside the postmortem document**, not in the
  team's actual work-tracking system (sprint board, ticket queue), so
  they're invisible during normal planning and only resurface when
  someone happens to reread old postmortems.
- **No recurring review mechanism checks open action items' age** --
  there's no forcing function (a monthly incident-review meeting, an
  automated stale-ticket report) that surfaces items rotting past their
  due date.
- **Action items are written too large/vague to ever fit into a sprint**
  ("improve deployment safety") so they never get picked up over
  concretely-scoped feature work, versus a properly scoped item ("add a
  pre-deploy smoke test for service X").
- **Completing the item was deprioritized by someone with the authority
  to do so, but that decision was never made explicit or revisited** -- it
  just quietly stalled rather than being consciously accepted as risk.

## Diagnose
1. Pull every postmortem from the last 6-12 months and list their action
   items with status. Compute the fraction still open past their stated
   due date -- this single number tells you if this is systemic.
2. For open items, check where they actually live: only in the
   postmortem doc, or also as a ticket in the team's real backlog with an
   assignee? Items that never made it into the backlog are effectively
   invisible and will not get done by accident.
3. For items open more than one full planning cycle, check whether
   deprioritization was ever explicit (a comment, a decision log entry)
   or just silent drift.
4. Cross-reference recent incidents against old postmortems' action
   items: does the new incident match a category an old, still-open item
   was meant to prevent? This is the direct evidence of cost.

## Fix
Treat every postmortem action item as a real ticket from the moment the
postmortem is approved: create it in the same tracker the team uses for
regular work, with a single named owner and a due date, not "the team" or
"someday." Scope each item small enough to fit in a normal sprint --
break "improve deployment safety" into the specific gate or check that
was actually missing. Add a recurring, lightweight review (part of an
existing weekly/monthly ops meeting is enough) that lists all open
incident-action-items past due and requires each to be either scheduled,
explicitly re-scoped, or consciously deprioritized with a stated reason
-- silence is not an acceptable status. This works because the failure
mode isn't lack of intent, it's the item having no mechanism competing
for attention against normal roadmap work; give it the same mechanism
(tracker, owner, due date, review) that roadmap work already has.

## Pitfalls
Don't create a separate, parallel "postmortem action item tracker" that
nobody checks during normal planning -- that just relocates the same
invisibility problem to a different tool. Also avoid rubber-stamping
items as "done" when only a partial mitigation shipped (e.g. an alert was
added but the underlying race condition wasn't fixed) -- verify the item
actually addresses the systemic cause it was written for, not just that
some commit references the ticket number.

## Verify
Pick a sample of "closed" action items from the last quarter and confirm
each one's described fix is actually live in production (not just merged
to a branch, not just partially rolled out) by checking the relevant
config/code/dashboard directly. Track the open-past-due-date percentage
monthly; a working fix shows it trending toward zero and staying there,
not just a one-time cleanup spike.
