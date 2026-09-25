---
name: proactive-rewrite-without-business-justification
description: A working legacy system is rewritten proactively without a clear business justification, consuming significant engineering time and introducing new bugs the stable original system didn't have.
triggers: ["rewrite without clear justification", "rewrote working system introduced new bugs", "engineering time spent on unjustified rewrite", "legacy system worked fine before rewrite"]
permissions: ["READ"]
---

## Symptom

A legacy system that was stable and "just worked" (even if the code
itself was unpopular with the team) gets rewritten based primarily on
engineering discomfort with old code, consuming significant time -- and
the new system, despite being "cleaner," introduces new production bugs
the old, unglamorous system never had, with no corresponding business
outcome (new capability, meaningfully better performance, resolved
compliance issue) that justified the investment and risk.

## Likely causes

- **The rewrite was motivated primarily by engineering preference**
  (dislike of the old code style/language/framework, desire to use a
  newer technology) rather than a specific, articulable business problem
  the old system was actually causing.
- **No cost-benefit analysis was done before committing to the rewrite**
  -- the engineering time cost and risk of introducing new bugs into a
  previously-stable system was never explicitly weighed against what
  business value the rewrite would actually unlock.
- **"Technical debt" was invoked as a justification without being tied
  to a concrete, measurable problem** (a specific recurring bug category,
  a specific feature that's genuinely hard to build on the old system),
  making the rewrite decision hard to evaluate or challenge on its
  actual merits.
- **Rewriting felt like a safer/more interesting way to spend time than
  the actual highest-value available work**, especially if the
  alternative was less appealing (maintaining/extending unfamiliar
  legacy code) even though it might have been the better use of time.

## Diagnose

1. Identify what specific, concrete problem (if any) the rewrite was
   originally justified by, and assess whether that problem was real
   and whether the rewrite actually solved it.
2. Compare the bug rate/incident history of the old system (before the
   rewrite) against the new system (after) for a comparable time period,
   to get concrete evidence of whether the rewrite actually improved
   reliability or made it worse.
3. Calculate the actual engineering time spent on the rewrite and compare
   against what alternative work could have been done with that same
   time, to make the opportunity cost concrete.
4. Interview stakeholders (product, business) for whether the rewrite
   unlocked anything they actually needed, versus being an internal
   engineering-only initiative with no external-facing justification.

## Fix

For the current situation, focus on stabilizing the new system (fixing
the specific new bugs it introduced) since reverting to the old system
is usually not practical once significant migration has happened.
Going forward, require an explicit, concrete business or technical
justification (a specific measured problem, not general "technical
debt" discomfort) before committing to a full rewrite, and do a
lightweight cost-benefit assessment comparing the rewrite's cost/risk
against targeted alternative investments (incremental refactoring of the
specific problematic parts, rather than a full rewrite) that might solve
the same concrete problem with less risk.

## Pitfalls

Don't swing to the opposite extreme of refusing any modernization work on
legacy systems purely because one unjustified rewrite went poorly --
some legacy systems genuinely do need rewriting for concrete reasons
(a real, measured bug pattern, a real blocker to needed new
capabilities); the fix is requiring justification and cost-benefit
analysis, not banning rewrites categorically.

## Verify

Track the new system's bug/incident rate over the following months and
confirm it trends toward (and ideally below) the old system's historical
rate, as evidence the investment is paying off despite the rocky start.
For future proposed rewrites, confirm the required justification and
cost-benefit analysis is actually being done and reviewed before
approval, not treated as a formality.
