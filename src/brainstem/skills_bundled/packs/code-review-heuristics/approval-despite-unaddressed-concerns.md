---
name: approval-despite-unaddressed-concerns
description: A reviewer approves a pull request primarily to avoid blocking a teammate or appearing difficult, despite having genuine unaddressed concerns that later contribute to a preventable bug.
triggers: ["approved despite concerns to avoid blocking", "reviewer had doubts but approved anyway", "social pressure approve pr", "reviewer did not want to seem difficult"]
permissions: ["READ"]
---

## Symptom

After a bug is traced back to a specific merged PR, it emerges (often
informally, in a postmortem conversation) that the reviewer who approved
it actually had genuine reservations at the time -- but approved anyway
rather than blocking, out of reluctance to hold up a teammate, appear
overly critical, or escalate a disagreement.

## Likely causes

- **Team culture implicitly discourages blocking/requesting changes**,
  treating it as socially costly (seen as difficult, obstructive, or
  distrustful) rather than a normal, expected part of a healthy review
  process, so reviewers self-censor legitimate concerns to avoid that
  social cost.
- **The reviewer wasn't fully confident their concern was valid**
  (uncertain whether it was a real issue or just their own
  unfamiliarity with the approach) and defaulted to approving rather
  than raising an uncertain objection, especially against a more senior
  or more confident author.
- **Time pressure on the author (a deadline, a blocking dependency) was
  visible to the reviewer**, and the reviewer weighed the author's
  visible urgency against their own less-certain concern and let the
  urgency win.
- **No low-friction way exists to express "approve, but I have a concern
  worth discussing"** -- the tooling/culture presents review as a binary
  block-or-approve decision, pushing genuine but non-blocking concerns
  toward silence rather than being voiced.

## Diagnose

1. In the postmortem/retrospective for the specific bug, directly ask
   the reviewer whether they had any hesitation at review time, and if
   so, what it was and why it wasn't raised or acted on.
2. Check team culture/history for whether "requesting changes" or
   pushing back is treated as normal versus something that generates
   social friction, based on how past instances of it were received.
3. Check whether the review tooling supports a distinct "approve with
   comment/concern" state versus a binary approve/block, and whether
   it's actually used when appropriate.
4. Assess whether visible author time pressure is a recurring factor in
   similar situations, suggesting a systemic pattern rather than a
   one-off.

## Fix

Explicitly normalize and reward raising concerns during review, even
uncertain ones, by making clear (through team norms and leadership
modeling) that flagging a possible issue is valued regardless of
whether it turns out to be a real problem -- the cost of a raised-but-
unfounded concern is far lower than a missed real one. Use (or adopt) a
review tool feature that supports "approve with non-blocking comment,"
giving reviewers a way to voice a concern on record without feeling they
must either fully block or stay silent. Address the underlying time-
pressure dynamic separately (see this pack's slow-turnaround skill) so
authors' visible urgency doesn't structurally pressure reviewers into
silence.

## Pitfalls

Don't respond by requiring reviewers to block on any uncertainty, which
would overcorrect into excessive blocking and slow the team down for
low-stakes disagreements -- the goal is making it safe and normal to
*voice* a concern, not mandating that every concern must halt merge.

## Verify

Track how often reviewers use an "approve with concern" mechanism (if
adopted) over subsequent months as one proxy for whether concerns are
now being surfaced rather than silently swallowed. In postmortems for
future incidents, explicitly ask whether any reviewer had unaddressed
hesitation, and track whether that pattern recurs less often over time.
