---
name: slow-review-turnaround-causes-pr-batching
description: Review turnaround time is slow enough that authors start batching multiple unrelated changes into one pull request to reduce review overhead, making each PR harder to review well.
triggers: ["authors batching prs due to slow review", "review turnaround too slow", "pr contains unrelated changes because review is slow", "slow reviews causing larger prs"]
permissions: ["READ"]
---

## Symptom

Pull requests increasingly contain multiple unrelated changes bundled
together (a bug fix plus a refactor plus a small feature) rather than
one focused change per PR -- and asking authors why reveals they're
doing this deliberately to avoid the overhead of going through the slow
review process multiple times for what would otherwise be several
separate, smaller PRs.

## Likely causes

- **Review turnaround time (time from PR opened to first substantive
  feedback, or to approval) is slow enough that authors experience real
  cost each time they open a new PR** -- context-switching away from
  other work while waiting, or simply the calendar time lost -- making
  batching a rational individual response to a slow process.
- **Reviewer capacity is genuinely constrained** (too few people
  available to review relative to PR volume, or review isn't prioritized
  against other work), so turnaround time is a real resourcing problem,
  not just a process issue.
- **No SLA or expectation exists for review turnaround time**, so there's
  no shared target that would make slow turnaround visible as a problem
  worth fixing rather than an accepted status quo.
- **Batching itself compounds the problem** -- a batched PR takes longer
  to review than the sum of what its individual pieces would have taken
  separately, since a reviewer has to context-switch between unrelated
  concerns within the same review session, creating a vicious cycle
  where slow review causes batching, which causes slower review.

## Diagnose

1. Measure actual review turnaround time (median and tail) across recent
   PRs to establish a concrete baseline, not just an impression.
2. Correlate PR size/scope-mixing with turnaround time historically --
   confirm whether batched PRs actually take proportionally longer to
   review than the sum of their parts would have.
3. Interview authors who batch changes to confirm the actual motivation
   (avoiding review overhead specifically, versus other reasons like
   convenience).
4. Assess reviewer capacity relative to PR volume to determine whether
   the root cause is a resourcing gap or a process/prioritization gap.

## Fix

Establish an explicit review turnaround SLA/expectation (e.g. first
response within one business day) and track adherence, making slow
turnaround visible and addressable rather than an invisible norm.
Address the underlying resourcing gap if reviewer capacity is genuinely
insufficient (more people doing review, review time protected/prioritized
in individual schedules) rather than only addressing the symptom.
Explicitly encourage and normalize small, focused PRs by making it clear
that review overhead per PR isn't actually the bottleneck once turnaround
is fixed -- the fix for batching is fixing turnaround, not asking authors
to batch less while turnaround stays slow.

## Pitfalls

Don't respond to slow turnaround by simply asking authors to "just open
smaller PRs" without fixing the underlying turnaround problem -- that
asks people to accept more individual review-request overhead without
addressing why batching felt necessary in the first place, and the
advice won't stick under the same pressure that caused batching.

## Verify

After improving turnaround time (via SLA/prioritization/capacity fixes),
measure whether PR size and scope-mixing trends back down toward smaller,
more focused PRs, confirming batching was genuinely a turnaround-driven
behavior rather than an unrelated habit. Track turnaround SLA adherence
over subsequent months to confirm the improvement is sustained.
