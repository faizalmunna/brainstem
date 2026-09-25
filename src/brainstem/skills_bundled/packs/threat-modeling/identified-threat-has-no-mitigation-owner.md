---
name: identified-threat-has-no-mitigation-owner
description: A threat model correctly identifies a real risk, but no specific person or team is assigned to fix it and no deadline is set, so it sits in a document indefinitely with no follow-through.
triggers: ["this threat has been in the doc for a year with no owner", "who's actually supposed to fix this finding", "the threat model has a bunch of unassigned risks", "we identified this but nothing happened"]
permissions: ["READ"]
---

## Symptom
A specific, well-described threat has sat in the threat model document, unchanged, across multiple review cycles or even a security incident near-miss. Everyone who reads it agrees it's real and worth fixing, but when asked "who is working on this," the answer is a shrug — it's not on anyone's sprint board, not in anyone's OKRs, and re-appears identically in the next quarterly review with the same "open" status it had a year ago.

## Likely causes
1. **Threat model output isn't connected to the team's actual work-tracking system** — findings live in a spreadsheet, wiki page, or slide deck that nobody's day-to-day workflow touches, so even a well-understood, agreed-upon risk never becomes a ticket in the backlog where engineering work actually gets scheduled and prioritized against other work.
2. **Ambiguous ownership across team boundaries** — the threat spans multiple systems or teams (e.g., "the auth team's token issuance combined with the API gateway's validation gap"), and because no single team clearly owns the fix end-to-end, it's assumed to be someone else's responsibility by everyone who sees it.
3. **No deadline or SLA tied to severity** — even findings marked "high" have no target remediation date, so they compete against dated feature deadlines and lose every time, since there's no forcing function analogous to a sprint commitment.
4. **The review meeting produces a decision to "accept" or "track" the risk informally, but that decision is never recorded with a name and date attached** — verbal agreement in a meeting ("yeah, we should look at that") is mistaken for an actual assignment, and it evaporates once the meeting ends.

## Diagnose
1. Open the threat model and check every entry for an assigned owner field and a target date field. Count how many are blank or list a team name instead of an individual/role accountable for tracking it.
2. For the threats marked as high-priority in the last review, search the team's actual issue tracker (Jira, Linear, GitHub Issues) for a corresponding ticket. Compute the ratio of high-priority threats with a live ticket versus those that exist only in the threat model document — a large gap confirms the disconnect.
3. Pick one long-standing unassigned threat and ask two different teams who's responsible for it. If they give different answers (or both say "not us"), that's the cross-team ownership gap in action.
4. Check the threat model's revision history for that specific entry — if its status field has been copy-pasted unchanged across several review dates, it's confirmed stalled rather than actively being worked.

## Fix
Require that every threat crossing an agreed severity threshold gets converted into an actual ticket in the team's real work-tracking system at the moment it's identified — not "eventually," but as a mandatory output of the review meeting itself, with an owner (a named person or a specific team's on-call/lead, not a vague "platform team") and a target remediation window keyed to severity (e.g., high severity gets a fixed SLA measured in weeks, not left open-ended). For threats spanning multiple teams, explicitly assign one team as the accountable owner for coordinating the fix even if other teams contribute, so "not us" is never a valid answer during follow-up. Bring the threat model document into the same review cadence as other engineering risk (e.g., reviewed in the same forum as incident action items) so unassigned or overdue threats surface automatically instead of requiring someone to remember to check the document.

## Pitfalls
Assigning ownership to a team rather than a specific accountable person often just relocates the diffusion of responsibility one level down — "the platform team owns it" can be just as unowned in practice as no owner at all if no individual is tracking it. Also avoid the trap of treating "we discussed it and everyone agrees it's important" as equivalent to assignment; agreement without a named owner and date recorded in the tracking system is not a mitigation plan, it's a shared feeling that fades by the next meeting.

## Verify
Sample five threats currently marked open in the model and confirm each has a linked ticket with a named assignee and a due date in the team's actual issue tracker, and that the due date is not already significantly past without a documented re-negotiation (extended date plus reason, not silence).
