---
name: findings-repeat-year-over-year-no-root-cause-fix
description: The same category of vulnerability appears in penetration test reports year after year across different specific instances, because each finding is fixed individually without addressing the systemic root cause.
triggers: ["same vulnerability type every year", "pentest findings recurring pattern", "fixing symptoms not root cause security", "annual pentest same category of issues"]
permissions: ["READ"]
---

## Symptom

Comparing penetration test reports across multiple years shows the same
category of vulnerability (a specific class of injection flaw, a
recurring pattern of missing authorization checks, a repeated secrets-
management mistake) appearing in different specific locations each time
-- each individual instance gets fixed, but the underlying pattern that
keeps producing new instances is never addressed.

## Likely causes

- **Each finding is fixed as an isolated bug** (patch the specific
  vulnerable code) without anyone asking "why does this keep happening"
  or investigating whether the same mistake exists elsewhere in the
  codebase or will be reintroduced by future code written the same way.
- **No systemic fix was applied** -- a framework-level guardrail, a
  linter rule, a secure-by-default library wrapper -- that would prevent
  the entire category of mistake going forward, so new code continues to
  be written the same vulnerable way that produced the previous
  instances.
- **Developer training/awareness about the recurring vulnerability
  category is insufficient**, so new code (or new developers unfamiliar
  with past findings) keeps reproducing the same class of mistake without
  realizing it's a known, recurring pattern for this team/codebase.
- **The organization doesn't track vulnerability categories across
  engagements over time**, so the recurring pattern itself was never
  visible as a pattern -- each report was reviewed in isolation without
  anyone comparing it against prior years' findings.

## Diagnose

1. Compile findings across multiple years of penetration test reports
   and categorize them by vulnerability type/root cause pattern, to
   confirm and quantify which categories are genuinely recurring versus
   one-off.
2. For a specific recurring category, check whether previous instances
   were fixed with a point patch or with any broader, systemic change
   (a linter rule, a secure wrapper, a framework guardrail).
3. Check whether any developer training or documentation exists
   specifically addressing the recurring category, and whether it's
   actually been delivered to the team.
4. Search the current codebase for other, not-yet-discovered instances of
   the same pattern, to confirm the systemic risk extends beyond what's
   been found so far.

## Fix

For a confirmed recurring vulnerability category, implement a systemic
guardrail that prevents the entire class of mistake rather than only
fixing individual instances -- a linter/static-analysis rule that flags
the dangerous pattern automatically, a secure-by-default library wrapper
that makes the safe way the easy way, or a framework-level control that
removes the developer's ability to make the mistake at all. Proactively
search the codebase for other undiscovered instances of the same pattern
rather than waiting for the next penetration test to find them one at a
time. Track vulnerability categories across engagements over time
explicitly (a simple running log) specifically to make recurring
patterns visible as patterns, not just as isolated annual findings.

## Pitfalls

Don't treat training alone as sufficient to prevent recurrence -- human
awareness/training helps but reliably fails to prevent a systemic
pattern at scale; prioritize automatable guardrails (linters, secure
defaults) that don't depend on every individual developer remembering a
past lesson.

## Verify

After implementing a systemic guardrail (e.g. a linter rule), confirm it
actually catches a reintroduced instance of the pattern in a test PR
before merge. Track the specific vulnerability category across the next
one or two penetration test cycles and confirm it stops appearing as a
new finding, or appears at a meaningfully reduced rate.
