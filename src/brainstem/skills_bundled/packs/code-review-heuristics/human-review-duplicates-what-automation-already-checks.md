---
name: human-review-duplicates-what-automation-already-checks
description: Human code review time is spent on issues automated checks (linting, tests, security scanning) already catch, instead of the higher-value things only a human can evaluate.
triggers: ["reviewer commenting on things linter should catch", "review time wasted on automatable issues", "human review duplicating ci checks", "review not focused on architecture or logic"]
permissions: ["READ"]
---

## Symptom

Reading through code review comment history shows a significant fraction
of human reviewer time and comments spent on issues that automated
tooling (a linter, a formatter, a static analyzer, a security scanner)
already catches or could easily catch -- while genuinely human-judgment-
requiring aspects (architecture fit, business logic correctness,
non-obvious edge cases) receive comparatively little attention.

## Likely causes

- **Automated checks exist but aren't actually gating merge**, so
  passing CI doesn't guarantee they were addressed, leaving human
  reviewers to catch the same issues manually as a backstop, duplicating
  effort that automation should have made unnecessary.
- **The available automated tooling doesn't cover certain common issue
  categories** that keep showing up in human review comments, revealing
  a gap where a new linter rule or static analysis check could be added
  but hasn't been.
- **Reviewers haven't fully internalized that certain checks are
  automated already**, so out of habit or uncertainty they manually
  re-verify things a quick look at CI status would already confirm.
- **No clear separation exists between what CI covers and what's
  explicitly reserved for human judgment**, so reviewers default to
  checking everything themselves rather than trusting and building on
  top of automated coverage.

## Diagnose

1. Categorize a sample of review comments (automatable-and-should-be-
   caught-by-tooling vs. genuinely requires-human-judgment) to quantify
   how much reviewer effort is going toward the former.
2. For comments in the automatable category, check whether a
   corresponding automated check exists and is actually gating merge, or
   whether it's genuinely missing from the toolchain.
3. Check whether CI status is clearly visible to reviewers at the point
   they're reviewing, and whether failing/missing checks would actually
   block merge independent of human approval.
4. Interview reviewers about their habits -- do they trust CI enough not
   to manually re-check what it covers, or do they check anyway out of
   uncertainty?

## Fix

Add or strengthen automated checks for any issue category that keeps
recurring in manual review comments but doesn't yet have tooling
coverage, and ensure all such checks are actually required/gating for
merge (not just informational). Make CI status clearly and prominently
visible in the review interface so reviewers can quickly confirm
automated coverage rather than re-deriving it. Explicitly communicate to
the team which categories of issues are "automation's job" versus
"human judgment's job," so review effort is deliberately directed at the
latter.

## Pitfalls

Don't assume automated tooling coverage means human reviewers should stop
looking at a category entirely -- automated checks have false negatives
too, and some judgment (is this the *right* approach, not just a
syntactically valid one) still benefits from occasional human attention
even in areas tooling mostly covers; the goal is rebalancing effort, not
eliminating human attention from covered areas entirely.

## Verify

After adding new automated checks for previously-manual issue
categories, sample review comments again over subsequent PRs and confirm
the proportion of comments in the automatable category drops while
architecture/logic-focused comments make up a larger share of the
remaining review effort.
