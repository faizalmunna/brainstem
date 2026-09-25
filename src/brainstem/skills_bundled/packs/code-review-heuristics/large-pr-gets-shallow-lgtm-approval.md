---
name: large-pr-gets-shallow-lgtm-approval
description: A pull request with hundreds of changed lines receives a quick approval because reviewers are cognitively unable to meaningfully review something that size, and a real bug ships inside it.
triggers: ["large pr got rubber stamped", "big pr approved too quickly", "bug shipped in huge pull request", "reviewer could not meaningfully review large diff"]
permissions: ["READ"]
---

## Symptom

A pull request with an unusually large diff (hundreds or thousands of
changed lines) receives approval within minutes, with review comments
that are sparse or entirely absent -- and a real bug that a careful
review would likely have caught ships as part of it, discovered only
after merge.

## Likely causes

- **Human reviewers have a well-documented cognitive limit on how much
  diff they can meaningfully evaluate at once** -- research on code
  review effectiveness consistently shows review quality drops sharply
  past a few hundred lines, so a large PR is structurally set up for
  shallow review regardless of the reviewer's diligence or skill.
- **The PR bundles multiple unrelated changes together** (a refactor plus
  a feature plus an unrelated fix), making it hard for a reviewer to
  build a coherent mental model of what's actually changing and why,
  compounding the sheer size problem with a comprehension problem.
- **Social/time pressure pushes toward fast approval** -- the PR author
  is blocked waiting, the reviewer has other priorities, and "LGTM"
  becomes the path of least resistance when a genuinely thorough review
  would take much longer than anyone has budgeted for it.
- **No norm or tooling exists that flags oversized PRs for extra
  scrutiny or encourages splitting them**, so there's no structural
  nudge counteracting the natural pressure to approve quickly.

## Diagnose

1. Measure the actual size (lines changed, files touched) of PRs that
   later needed a bug fix shortly after merge, and compare against the
   review time/comment count they received, to establish whether size
   correlates with shallow review in this specific team's history.
2. Check whether the specific bug that shipped was in a part of the diff
   that would have been genuinely hard to spot given the PR's total size,
   or whether it was actually fairly visible and simply wasn't looked at
   carefully.
3. Review whether the PR bundled multiple unrelated changes, and whether
   splitting it would have made the bug's location more obvious.
4. Check team norms/tooling for whether PR size is tracked or flagged at
   all currently.

## Fix

Establish a practical PR size guideline (not a hard rule, but a strong
norm) and tooling that flags PRs exceeding it for either splitting or
explicit extra review time allocation. Encourage/require large,
unavoidable changes (a genuine large refactor) to be split into a
sequence of smaller, independently reviewable PRs where the change
allows it, or accompanied by a clear summary that walks a reviewer
through the logical structure of the change rather than leaving them to
reconstruct it from the raw diff. Make it socially acceptable and
expected to say "this needs more time" or "this should be split" rather
than defaulting to quick approval under time pressure.

## Pitfalls

Don't respond to this by making a hard, unbendable line-count limit that
blocks all larger PRs -- some changes (a large but mechanical rename, a
generated file update) are genuinely low-risk despite size, and a rigid
rule creates friction without proportionate benefit; use size as a
signal for extra scrutiny, not an automatic block. Also don't just tell
reviewers to "review more carefully" without addressing the structural
size/bundling problem -- that puts the burden entirely on individual
diligence rather than fixing the systemic cause.

## Verify

Track PR size distribution and post-merge bug rate over subsequent
months and confirm a reduction in large, unsplit PRs correlates with
fewer bugs discovered shortly after merge. Spot-check a sample of large
PRs under the new norm to confirm they're either being split or
receiving genuinely proportionate review time/attention.
