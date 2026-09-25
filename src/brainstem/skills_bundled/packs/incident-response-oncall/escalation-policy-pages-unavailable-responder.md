---
name: escalation-policy-pages-unavailable-responder
description: An escalation policy pages someone who is on vacation or otherwise unavailable with no fallback, delaying incident response.
triggers: ["paged someone on vacation", "on-call schedule wasn't updated", "nobody responded to the page", "escalation policy has no fallback", "page went to the wrong person"]
permissions: ["READ"]
---

## Symptom
An alert fires and pages the on-call engineer per the schedule, but that
person is on vacation, at a conference, or otherwise unreachable, and
either doesn't have the app installed/muted their phone, or was never
actually swapped out of the rotation despite requesting time off. The
page goes unacknowledged for the full escalation timeout (often 10-20
minutes) before it falls through to a secondary responder, if one is even
configured -- by which point the incident has been actively worsening,
unattended, the whole time.

## Likely causes
- **The on-call schedule and the team's actual availability calendar are
  separate systems that don't sync** -- someone requests PTO in an HR
  tool or team calendar, but the on-call rotation tool isn't updated, so
  the schedule still assigns them.
- **Swaps are handled informally** ("hey can you cover Tuesday for me,"
  agreed over chat) but never actually entered into the paging system, so
  the system's source of truth doesn't match reality.
- **No secondary/backup escalation tier is configured at all** -- if the
  primary doesn't acknowledge, there's nowhere for the page to go except
  to keep re-notifying the same unreachable person, or it silently stops.
- **The escalation timeout is too long relative to incident severity** --
  even with a working fallback tier, waiting the full default timeout
  before trying the next person wastes minutes that matter for a
  high-severity page.
- **Multiple independent alerting tools each have their own
  separately-configured on-call schedule**, and only one of them was
  updated for a given absence, so the specific alert that fired happened
  to use the stale one.

## Diagnose
1. Pull the timeline of the missed page: when it fired, when (if ever) it
   was acknowledged, and by whom -- confirm the gap and who it was
   originally routed to.
2. Check that person's actual availability at the time (calendar, PTO
   system) against what the paging tool's schedule shows for that
   window -- a mismatch confirms a sync/update failure rather than a
   one-off missed notification.
3. Check whether a secondary escalation tier exists in the policy at all,
   and if so, how long the primary tier waits before falling through --
   compare that timeout against the incident's actual severity/urgency
   requirements.
4. If multiple alerting tools are in use, check whether the specific tool
   that fired this alert was included in whatever swap/update process was
   followed, or only the "main" one was updated.

## Fix
Make the on-call paging schedule the single source of truth for
availability by integrating it directly with whatever system tracks
PTO/absence (calendar sync, or requiring schedule changes through the
paging tool itself as part of the PTO request workflow) rather than
relying on separate informal coordination. Always configure at least one
fallback tier (a secondary individual, then a team-wide/manager
escalation) so an unacknowledged page never dead-ends on a single person,
and set escalation timeouts proportional to severity -- shorter for
pages tied to high-severity alerts. Where multiple alerting tools each
maintain their own on-call configuration, either consolidate to one
system routing all pages, or establish a single checklist step for any
schedule change that explicitly covers every tool in use, so an update
can't be made in one and missed in another.

## Pitfalls
Don't rely purely on "people will remember to update it" as the process
-- the fix has to remove the manual sync step, not just ask people to
be more diligent about a step that's already proven unreliable. Also
don't set the fallback tier to page an entire team indiscriminately as
the default first step -- that recreates alert fatigue for people not
actually on call; reserve broad paging for genuine fallback after a
defined primary timeout, not as the routine first action.

## Verify
Audit the on-call schedule against the team's actual PTO/calendar records
for the current and next rotation period and confirm they match with no
manual reconciliation required. Run a scheduled test page (a
"who's on call" drill, not a real incident) during a period when the
primary is intentionally unavailable and confirm it falls through to the
secondary within the configured timeout, for every alerting tool the team
uses, not just the primary one.
