---
name: vague-comment-causes-clarification-back-and-forth
description: A reviewer's comment describes a problem without suggesting a direction, leading to multiple clarification round-trips that slow down the review without improving its quality.
triggers: ["review comment too vague", "back and forth clarifying review feedback", "reviewer did not suggest a fix", "slow review from unclear comments"]
permissions: ["READ"]
---

## Symptom

A pull request's review takes many days and several rounds of comments
to resolve, not because the underlying issue was complex, but because
the reviewer's initial feedback described a problem vaguely ("this
feels off," "not sure about this approach") without suggesting what a
better direction would look like, forcing the author to guess, propose
something, and iterate multiple times before landing on what the
reviewer actually wanted.

## Likely causes

- **The reviewer identified that something was wrong but hadn't fully
  worked out what the right alternative was themselves**, so the comment
  reflects genuine but incomplete thinking, leaving the author to do the
  work of exploring alternatives that the reviewer could have
  contributed to directly.
- **The reviewer intentionally left the comment open-ended to avoid being
  overly prescriptive**, wanting to give the author room to find their
  own solution -- a reasonable intention that backfires when the
  underlying concern isn't specific enough for the author to know what
  problem they're actually solving for.
- **The comment style habitually favors brevity over specificity**
  (a general team or individual writing habit), consistently leaving
  out the "why" and "what instead" that would make feedback
  actionable in one pass rather than requiring follow-up questions.
- **The reviewer and author have different implicit context** about what
  "off" means in this situation, and the gap between their mental
  models isn't bridged by a vague comment, requiring several rounds of
  back-and-forth just to establish shared understanding before the
  actual technical resolution can happen.

## Diagnose

1. Read through the actual comment thread for the slow review and
   identify the specific point where the exchange became unproductive
   back-and-forth rather than converging.
2. Check whether the reviewer's initial comment named a specific concern
   (even if not a full solution) or was genuinely vague ("this feels
   off" versus "this doesn't handle the case where X is null").
3. Check how many total round-trips occurred and how much elapsed time
   each one took, to quantify the actual cost of the vagueness.
4. Ask the reviewer, after the fact, what they were actually thinking at
   the time of the original comment, to assess whether they had a
   specific concern that simply wasn't articulated, or a genuinely
   unformed one.

## Fix

Encourage a review comment habit that names the specific concern
concretely (what could go wrong, under what condition) even when not
proposing a full solution -- "I'm not sure about this" is much less
actionable than "what happens if X is null here?" even without offering
the fix. Where a reviewer does have a specific alternative in mind,
suggesting it directly (even as "have you considered X?" rather than a
mandate) saves round-trips compared to describing only that something
feels wrong. For genuinely open-ended architectural concerns, consider
moving the conversation to a quicker synchronous channel (a short call,
a chat thread) rather than iterating slowly through asynchronous PR
comments across multiple days.

## Pitfalls

Don't overcorrect into reviewers always being expected to provide a full
prescribed solution for every concern -- sometimes genuinely not knowing
the right answer but flagging that something needs more thought is
valid feedback; the fix is being as specific as possible about the
*concern*, not necessarily always having the *answer*.

## Verify

Track review round-trip count and elapsed time for reviews before and
after encouraging more specific initial comments, and confirm a
reduction in multi-round clarification cycles for comparable-complexity
PRs.
