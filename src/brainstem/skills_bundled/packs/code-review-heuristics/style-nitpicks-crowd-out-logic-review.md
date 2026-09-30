---
name: style-nitpicks-crowd-out-logic-review
description: Code review comments focus almost entirely on style and formatting while missing a genuine logic bug or security issue in the same pull request, because style issues are faster to spot.
triggers: ["review focused on style missed real bug", "nitpicks instead of real issues", "formatting comments but bug shipped", "style feedback crowding out logic review"]
permissions: ["READ"]
---

## Symptom

Reviewing the comment history on a pull request that later turned out to
have a real bug or security issue shows the actual review feedback was
almost entirely about style, naming, and formatting -- easy,
low-effort observations -- while the genuine logic problem sitting in
the same diff received no comment at all.

## Likely causes

- **Style and formatting issues are much faster and easier to spot than
  logic issues**, so under time pressure (or simply due to how human
  attention naturally allocates), reviewers gravitate toward the
  low-effort, high-visibility feedback first and often exhaust their
  available review time/attention before reaching deeper analysis.
- **No automated linting/formatting tooling exists (or isn't enforced)**
  to catch style issues automatically, leaving that burden entirely on
  human reviewers and consuming review bandwidth that should go to
  things automation genuinely can't catch.
- **Reviewers default to style feedback because it's socially safer**
  than raising a substantive logic concern -- a style comment is
  unambiguous and rarely provokes disagreement, while questioning the
  correctness of someone's logic can feel more confrontational,
  especially in a team culture that hasn't normalized that kind of
  direct technical pushback.
- **The reviewer genuinely didn't have the context or time to evaluate
  the logic deeply**, and style feedback was what was actually available
  to give within the time they had, functioning as a substitute for
  substantive review rather than a deliberate choice.

## Diagnose

1. Review the comment history on the specific PR that had the missed
   issue, and categorize each comment (style/formatting vs. logic/
   correctness vs. architecture) to confirm and quantify the imbalance.
2. Check whether automated linting/formatting is configured and enforced
   in CI -- if not, that's a direct, fixable reason style feedback is
   still manually necessary and consuming reviewer attention.
3. Check whether the missed logic issue was something that required deep
   context to spot, or whether it was reasonably visible to someone
   reading carefully -- this distinguishes a genuine difficulty problem
   from an attention-allocation problem.
4. Sample review comment patterns across several other PRs (not just the
   one with the missed bug) to see if the style-heavy pattern is
   systemic or specific to this one review.

## Fix

Automate as much style/formatting feedback as possible (linters,
formatters, auto-fixers run in CI) so human reviewers never need to
manually comment on anything a tool can already enforce, freeing their
attention for what only a human can evaluate -- correctness, architecture,
business logic, edge cases. Explicitly normalize direct technical
pushback on logic/correctness as a valued, expected part of review
culture (not a confrontation), so reviewers don't default to safer style
comments as a substitute. Consider a review checklist or prompt that
explicitly directs attention to correctness/security/edge-cases as a
required pass, separate from style, so it's not accidentally skipped.

## Pitfalls

Don't overcorrect by banning style comments from review entirely --
some style/consistency conversations are legitimately valuable and
not fully automatable (naming clarity, code organization); the fix is
automating what's mechanically enforceable and ensuring logic review
still happens, not eliminating style feedback altogether.

## Verify

After automating style enforcement, track review comment categories
across subsequent PRs and confirm the proportion of logic/correctness
comments increases relative to style comments. Track post-merge bug rate
for PRs reviewed under the new process compared to the historical
baseline.
