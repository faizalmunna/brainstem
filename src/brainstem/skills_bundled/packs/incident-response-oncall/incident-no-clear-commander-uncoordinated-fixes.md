---
name: incident-no-clear-commander-uncoordinated-fixes
description: An incident response drags on because no one holds the incident commander role, so multiple people independently try different fixes uncoordinated.
triggers: ["nobody is leading the incident", "everyone is trying different fixes", "no incident commander", "incident response is chaotic", "too many people changing things during outage"]
permissions: ["READ"]
---

## Symptom
During an incident, several capable engineers join and start
investigating and applying fixes in parallel -- one restarts a service,
another rolls back a deploy, a third changes a feature flag -- without
checking with each other first. Changes get made, un-made, and
re-made; it becomes unclear which change (if any) actually caused
recovery when things do improve; and the incident runs longer than the
sum of the individual fix attempts would suggest, because effort is
duplicated and some changes interact badly with each other.

## Likely causes
- **No one was explicitly assigned the incident commander role**, so
  everyone defaults to acting on their own initiative, which is
  reasonable individually but produces uncoordinated action collectively.
- **The organization has an IC role defined on paper but no habit of
  actually invoking it** for incidents below the top severity tier, so it
  only shows up for the rare Sev1 and never for the more common
  Sev2/Sev3 incidents that still involve multiple responders.
- **The most senior/loudest person present starts directing informally,
  but without the explicit authority or the discipline of the IC
  role** (tracking hypotheses, sequencing changes, maintaining a
  single timeline) -- so it looks like coordination but lacks its
  structure.
- **Tooling makes it too easy to act unilaterally** -- anyone can deploy,
  roll back, or flip a flag without any coordination checkpoint, so the
  path of least resistance during stress is "just fix it myself" rather
  than "check with whoever's coordinating."

## Diagnose
1. Reconstruct the incident's change timeline from deploy logs, config
   change logs, and chat history: how many distinct changes were made by
   how many distinct people, and were they sequential (one at a time,
   observed) or overlapping (multiple in-flight at once)?
2. Check the incident channel/thread for whether anyone explicitly said
   "I'm coordinating this" or was designated as such -- absence of an
   explicit claim is the direct signal of no IC.
3. Look for contradicted or reverted changes within the same incident
   (a rollback followed by a re-deploy, a flag flipped and flipped back)
   -- this is strong evidence of uncoordinated, overlapping action.
4. Ask responders after the fact which specific change they believe
   fixed the issue -- if multiple people give different, equally
   plausible answers, the lack of sequencing during the incident made it
   impossible to actually know.

## Fix
Establish an explicit incident commander role that gets assigned (not
assumed) as soon as more than one or two people are actively responding,
regardless of official severity tier -- the trigger should be "multiple
responders," not "top severity only." The IC's job is specifically not to
personally fix the issue, but to maintain a single view of what's been
tried, sequence proposed changes one at a time so effects can be
attributed, and make explicit "who is doing what right now" visible to
everyone in the incident channel. Make claiming the IC role trivial (a
single command/bot interaction that announces it to the channel) so it
doesn't require a meeting or formal process to invoke. Route
change-making through a quick "I'm about to do X" announcement even if
informal, so the IC (or the group) can catch two people about to make
conflicting changes before they happen.

## Pitfalls
Don't make the IC the sole person allowed to type any command --
that creates a bottleneck when the IC isn't the most technically
qualified person for a given fix. The IC coordinates and sequences;
domain experts still execute. Also don't treat IC as a permanent
role tied to seniority -- anyone trained in the role should be able to
take it for a given incident, otherwise it becomes unavailable exactly
when the usual person is unreachable, recreating the same coordination
gap.

## Verify
Review the next incident with 3+ responders for whether an IC was
explicitly claimed early and whether the change timeline shows
sequential, attributable actions rather than overlapping ones. A working
fix shows a single coherent narrative in the postmortem of what was tried
in what order and why, rather than "several things were changed around
the same time and it started working."
