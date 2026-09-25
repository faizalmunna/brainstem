---
name: sast-noise-causes-tool-abandonment
description: A SAST tool newly wired into CI dumps hundreds of findings on first scan and the team disables the gate instead of triaging them.
triggers: ["sast has too many false positives", "we turned off the security scanner", "first scan found 500 findings", "nobody looks at the sast results anymore", "static analysis noise overwhelming team"]
permissions: ["READ"]
---

## Symptom
A SAST tool (Semgrep, CodeQL, SonarQube, Checkmarx, Fortify) gets added
to CI for the first time, immediately reports several hundred (or
thousand) findings against the existing codebase, and within a few
weeks the team either sets the CI job to `continue-on-error`, mutes the
Slack channel it posts to, or quietly removes it -- not because the tool
is broken, but because the initial backlog was never triaged down to a
manageable, trustworthy signal.

## Likely causes
1. **The tool was pointed at the entire history/codebase on day one**
   instead of being scoped to new/changed code first, so the first run
   surfaces years of accumulated pre-existing findings all at once
   rather than a reviewable trickle.
2. **Default rule pack is too broad for the stack** -- generic
   cross-language rule sets (or a language's "all rules" preset) include
   many low-value or stack-inapplicable checks (e.g. rules for a
   templating engine the project doesn't use) that inflate the count
   without adding signal.
3. **No baseline/suppression mechanism was established before rollout**,
   so every existing finding looks exactly as urgent as a finding in
   code written yesterday, and there's no way to distinguish "known,
   accepted, pre-existing" from "new, needs review."
4. **No owner was assigned to triage the backlog** -- the tool posts
   results into a channel or dashboard nobody has time allocated to
   review, so the queue only grows and eventually gets ignored as a
   matter of practical necessity, not policy.

## Diagnose
- Pull the raw finding count from the tool's dashboard/report and split
  it by rule ID -- check whether a small number of rules account for a
  disproportionate share (a classic sign of one noisy, low-value rule
  rather than genuinely broad risk).
- Check whether the tool was run in "full scan" mode against the whole
  repo or in "diff/incremental" mode against only the PR's changed
  lines -- most SAST tools support both, and CI integration guides
  default to full scan unless configured otherwise.
- Sample 15-20 findings at random and manually classify each as true
  positive, false positive, or "technically true but not exploitable
  here" -- this ratio is the actual signal quality, not the raw count.
- Check whether the tool has a baseline/suppression file
  (`.semgrepignore`, SonarQube's "new code" period, CodeQL's suppression
  comments) and whether it's actually configured, versus the team
  assuming it exists by default.

## Fix
Adopt a "baseline then gate on new code" rollout pattern rather than
gating on the full backlog from day one: snapshot the current findings
as an accepted baseline (most tools support this -- SonarQube's "new
code" period, Semgrep's baseline commit, CodeQL's existing-alert
dismissal), configure CI to fail only on *newly introduced* findings
relative to that baseline, and separately track the pre-existing backlog
as a scheduled cleanup effort with its own priority, not a blocking
gate. This turns the tool from "wall of unreviewable noise" into "gate
that only stops you from adding new problems," which is what actually
gets developer buy-in. In parallel, tune the rule pack down from the
generic default to one scoped to the actual stack and turn off or
downgrade-to-warning any rule where the sampled true-positive rate is
low.

## Pitfalls
- Silently muting the tool's notifications instead of formally
  disabling the gate creates a worse state than either running it
  properly or not running it at all -- the org believes it has SAST
  coverage in its compliance/audit story while getting zero actual
  signal.
- Baselining everything and never returning to the backlog turns a
  temporary rollout accommodation into a permanent blind spot --
  schedule the backlog burn-down (even slowly) rather than treating the
  baseline as done forever.
- Tuning rules down to make the noise stop without checking the
  true-positive sample first risks silencing a rule category that was
  actually catching real bugs, not just noisy ones.

## Verify
After baselining and re-scoping, run the scan again and confirm CI only
flags findings in the diff of a test PR that intentionally introduces a
known-bad pattern (e.g. a hardcoded secret or unsanitized query) --
confirm it fails on that PR and does not re-surface the pre-existing
baseline findings, then check the true-positive rate on a fresh sample
of the next 10 new-code findings to confirm it's meaningfully higher
than the pre-tuning baseline.
