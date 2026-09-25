---
name: reviewer-approves-diff-without-running-code
description: A reviewer approves a pull request based on reading the diff alone, missing an issue that would have been obvious if they had actually checked out and run the code.
triggers: ["bug obvious if reviewer had run the code", "approved without testing locally", "diff looked fine but broke on run", "reviewer never checked out the branch"]
permissions: ["READ"]
---

## Symptom

A merged pull request has a bug (a broken test, a runtime error, a UI
issue) that's immediately obvious the moment the code is actually run,
but it was approved based on reading the diff alone -- the reviewer
never checked out the branch, ran the test suite locally, or exercised
the changed functionality directly.

## Likely causes

- **Reviewing a diff in a PR tool is significantly lower-friction than
  checking out the branch and running it locally**, so reviewers default
  to the easier path unless a specific reason prompts them to go
  further, especially for changes that look straightforward from the
  diff alone.
- **CI is trusted to catch anything that running the code would reveal**,
  but CI doesn't cover the specific issue (a UI/visual problem, a
  behavior only observable interactively, an environment-specific issue
  CI's environment doesn't reproduce) that manual execution would have
  caught.
- **No team norm or expectation exists for when a reviewer should
  actually run the code** versus when diff-reading alone is considered
  sufficient, so it's left to individual judgment that varies reviewer
  to reviewer and often defaults to the lower-effort option.
- **The change looked simple/low-risk from the diff**, leading the
  reviewer to (incorrectly, in this case) judge that running it wasn't
  necessary -- a judgment call that's right most of the time but wrong
  for the specific PR that shipped a bug.

## Diagnose

1. For the specific bug that shipped, determine concretely whether
   actually running the code (not just reading the diff) would have
   caught it, to confirm this is genuinely a "should have run it"
   situation rather than something even careful execution wouldn't have
   revealed.
2. Check what CI actually covers for this type of change, and identify
   the specific gap between what CI validates and what the bug actually
   was.
3. Check whether a team norm exists for when to run code locally during
   review, and if so, why it wasn't followed for this PR.
4. Assess whether the change genuinely looked low-risk from the diff
   (a reasonable judgment call that happened to be wrong) or whether
   there were visible signals suggesting more scrutiny was warranted.

## Fix

Establish clear guidance for when reviewers should run the code locally
(or exercise it in a preview/staging environment) rather than relying on
diff-reading alone -- typically for changes touching UI, user-facing
flows, or areas with known CI coverage gaps. Where practical, set up
automated preview environments for PRs (many CI/CD platforms support
this) so reviewers can interact with the actual running change without
the friction of a full local checkout, lowering the barrier to doing
this more often. Close the specific CI coverage gap that let this
particular bug through, if one exists, so future similar bugs are caught
automatically rather than depending on reviewer diligence.

## Pitfalls

Don't mandate that every single PR must be run locally regardless of
size/risk -- that adds meaningful friction to low-risk changes (a
documentation fix, a well-tested small change) without proportionate
benefit; scope the expectation to changes where execution genuinely adds
verification value beyond what CI and diff-reading already provide.

## Verify

Confirm the specific CI gap (if fixed) now catches an equivalent
reintroduced version of the original bug in a test PR. Track whether
adopting preview environments (if implemented) actually increases how
often reviewers interact with running code, via usage data from the
preview environment tooling.
