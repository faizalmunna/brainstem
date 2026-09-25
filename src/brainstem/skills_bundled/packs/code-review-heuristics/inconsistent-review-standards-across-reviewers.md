---
name: inconsistent-review-standards-across-reviewers
description: Code review feedback is inconsistent across different reviewers or PRs for the same team, with no shared understanding of what actually blocks merge versus what's merely a suggestion.
triggers: ["different reviewers different standards", "inconsistent code review feedback", "no agreement on what blocks merge", "review standards vary by reviewer"]
permissions: ["READ"]
---

## Symptom

The same kind of issue gets treated very differently depending on which
reviewer happens to review a given PR -- one reviewer blocks merge over
something another reviewer would approve without comment, or would only
raise as an optional suggestion -- causing friction, confusion about
expectations, and inconsistent code quality across the codebase
depending on who happened to review each change.

## Likely causes

- **No documented, shared definition exists for what categories of
  feedback are blocking versus optional/suggestive**, so each reviewer
  applies their own personal judgment about severity, which naturally
  varies between people even with good intentions.
- **Reviewers have different levels of experience/context with the
  specific codebase area**, so what looks like an obvious problem to one
  reviewer (who's seen it cause issues before) looks like a minor style
  preference to another who lacks that history.
- **No feedback mechanism exists for calibrating reviewer standards
  against each other** -- reviewers don't see how their peers handle
  similar situations, so drift between individual standards goes
  unnoticed and uncorrected over time.
- **Review comment conventions (a way to signal "this is blocking" vs.
  "this is just a thought") aren't used consistently**, so even when a
  reviewer intends a comment as optional, the PR author can't reliably
  tell the difference from one who intends it as a hard requirement.

## Diagnose

1. Sample review comments across several PRs and several different
   reviewers for the same category of issue (e.g. missing error
   handling, magic numbers) and compare how each was actually treated
   (blocking vs. ignored vs. suggested).
2. Interview a few reviewers directly about their personal mental model
   of what blocks merge, and compare answers across people to see how
   much they actually diverge.
3. Check whether any documented review standard/checklist exists at all,
   and if so, whether it's actually referenced/used in practice or
   exists only nominally.
4. Check whether the team uses any comment-labeling convention (like
   prefixing comments as "nit:", "blocking:", "question:") and how
   consistently it's applied.

## Fix

Document a shared, concrete review standard -- not an exhaustive style
guide, but a clear statement of what categories of issues are always
blocking (security issues, correctness bugs, missing tests for critical
paths) versus what's a suggestion the author can take or leave (naming
preferences, alternative approaches with no clear correctness
difference). Adopt and consistently use a comment-labeling convention so
severity is explicit on every comment rather than inferred. Periodically
calibrate as a team -- review a few past PRs together and discuss where
standards diverged, building shared judgment over time rather than
relying on a document alone.

## Pitfalls

Don't try to write an exhaustively detailed rulebook covering every
possible situation -- that becomes unmaintainable and still won't cover
every case; focus the shared standard on the genuinely high-stakes
categories (correctness, security) where consistency matters most, and
accept that some judgment-call variance on lower-stakes matters is
normal and doesn't need to be eliminated entirely.

## Verify

After introducing the shared standard and labeling convention, sample
review comments again across multiple reviewers for similar issue
categories and confirm more consistent treatment than before. Survey the
team informally for whether the "which reviewer you get" friction has
measurably decreased.
