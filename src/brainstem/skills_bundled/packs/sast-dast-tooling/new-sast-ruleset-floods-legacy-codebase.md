---
name: new-sast-ruleset-floods-legacy-codebase
description: Enabling a new SAST rule set retroactively flags thousands of pre-existing findings in legacy code all at once, making the tool feel punitive.
triggers: ["new rule pack broke the build for everyone", "sast update flagged 2000 old findings", "security tool suddenly punishing legacy code", "upgrading sonarqube quality profile failed the whole repo", "rule set update created a huge backlog overnight"]
permissions: ["READ"]
---

## Symptom
A SAST tool that had been running cleanly for months (or a newly
enabled stricter rule pack / quality profile / language version bump)
suddenly reports a large batch of findings against code that hasn't
changed -- not new commits, but files untouched in years -- because the
rule set itself changed underneath the existing codebase. Developers who
had nothing to do with the flagged code get build failures or a wall of
new backlog items attributed to them, and the tool starts feeling like
it's retroactively punishing old work rather than catching new mistakes,
which erodes trust in the tool overall.

## Likely causes
1. **A rule pack/quality profile update was applied globally without
   re-baselining** -- the scanner vendor shipped a new default rule set
   version (a scheduled update, a major version upgrade, switching to a
   stricter preset) and it was adopted without first checking how many
   *new* findings it would surface against the existing codebase.
2. **The CI gate re-evaluates the whole codebase on every run** rather
   than only new/changed code, so any rule-set change immediately
   applies retroactively to every historical line the next time CI runs,
   with no transition period.
3. **No changelog/diff review of the rule pack update was done before
   adopting it** -- teams often auto-update to "latest rules" (a
   `latest` tag, an auto-updating SaaS dashboard) without pinning and
   deliberately reviewing what changed, so a rule-set bump arrives as a
   surprise rather than a planned rollout.
4. **New findings get attributed to whoever's commit triggers the next
   scan**, not the original author of the flagged code, because blame
   tooling shows the last-touch commit -- making it look like recent
   contributors "introduced" old problems and drawing undeserved
   scrutiny.

## Diagnose
- Diff the rule pack/quality profile version between the last known-good
  scan and the one that produced the flood -- most tools log the profile
  version or ruleset hash used per scan, letting you confirm the jump
  precisely (e.g. Semgrep registry version bump, SonarQube quality
  profile change, a new CodeQL query pack release).
- Cross-reference the flagged files' last-modified/last-commit dates
  against the scan date -- a spike of findings in files with commit
  dates far older than the scan date confirms retroactive rule
  application rather than genuinely new code introducing the issues.
- Check whether the CI job re-scans the full codebase vs. diff-only, and
  whether a baseline/"new code" period setting exists and was reset or
  never configured for this rule pack specifically.
- Sample the flagged legacy findings for true-positive rate, same as any
  SAST rollout -- a new stricter rule pack can be a mix of genuinely
  valuable new coverage and overly strict/low-value new checks, and the
  response differs depending on which it mostly is.

## Fix
Treat a rule-set/quality-profile update exactly like a first-time SAST
rollout for the delta it introduces: before adopting a new rule pack
version in the CI-gating config, run it once in report-only/non-blocking
mode against the full codebase to measure how many new findings it adds
and at what true-positive rate; re-baseline those newly-surfaced legacy
findings (mark them as pre-existing/accepted-for-now, same mechanism as
initial rollout) so the *gate* only blocks on new code going forward, not
on legacy code the update newly touches; and pin rule pack versions
explicitly in config rather than tracking "latest," so future updates are
deliberate, reviewed adoptions rather than surprises. Communicate the
change to the team before it lands (a rule pack changelog summary) so a
sudden backlog doesn't read as arbitrary punishment.

## Pitfalls
- Rolling back the rule pack entirely to make the flood go away also
  throws away genuinely valuable new detection coverage -- prefer
  baselining the legacy delta over reverting the update wholesale, and
  only revert specific low-value rules identified via the true-positive
  sample.
- Assigning backlog cleanup tickets to whoever's name shows up via blame
  on flagged legacy code punishes people for old, often collectively-
  owned code -- route legacy backlog cleanup through a shared team
  queue, not individual blame-based assignment.
- Pinning rule versions and then never revisiting the pin creates the
  opposite long-term problem (missing newer detection coverage
  indefinitely) -- schedule periodic, deliberate rule-pack review
  instead of pinning forever.

## Verify
Confirm the CI gate no longer fails on the pre-existing legacy findings
by re-running it against a branch with only an unrelated, trivial change
(the pre-existing baseline findings should not block it), and confirm a
newly introduced test finding of the same rule category in a *new* line
of code still correctly fails the build -- proving the gate now
distinguishes newly-flagged-by-update-but-old code from genuinely new
violations.
