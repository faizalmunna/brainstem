---
name: security-gate-blocks-build-on-any-severity
description: A CI security gate fails the build on any finding regardless of severity, so developers routinely bypass or disable it under delivery pressure.
triggers: ["security gate blocking every deploy", "build fails on low severity finding", "developers bypassing the security check", "pipeline red because of a minor finding", "everyone adds skip-ci to get around scanner"]
permissions: ["READ"]
---

## Symptom
The CI pipeline's security scan step is configured as a hard pass/fail
gate that fails the whole build on *any* finding -- critical, medium, or
a purely informational one -- with no severity threshold. Developers
under deadline pressure start routinely working around it: adding
`[skip ci]` or a bypass label, disabling the step in their branch,
force-merging with admin override, or asking a security team member for
a one-off manual override so often that the override request itself
becomes the normal path, defeating the purpose of an automated gate.

## Likely causes
1. **The gate was configured with the scanner's default settings**,
   which often fail on any non-zero finding count out of the box, rather
   than a deliberately chosen severity threshold matched to actual risk
   tolerance and remediation SLAs.
2. **No distinction exists between "new" and "pre-existing" findings in
   the gate logic** -- even a low/no-severity-threshold gate becomes
   unworkable if it also re-evaluates the entire existing codebase on
   every build rather than only the changes in the current PR/commit.
3. **No override/exception path exists for legitimate cases** (a finding
   that's a known false positive awaiting suppression, or a fix that
   can't land before an urgent hotfix ships), so the only way to get
   urgent work through is to disable the gate entirely rather than use a
   scoped, audited exception.
4. **Severity ratings from the tool are taken at face value** without
   context -- many scanners default "medium" or even "high" for
   categories that are frequently false-positive-prone or low-impact in
   this specific codebase, inflating how often the gate trips on
   low-value findings.

## Diagnose
- Pull the gate's actual failure history from CI logs over the last
  1-2 months and classify each failure by the finding's real severity
  and whether it was new vs. pre-existing -- this quantifies whether the
  gate is mostly tripping on low-value noise or genuinely catching
  high-severity issues.
- Check how many times the gate was bypassed (admin override, disabled
  step, force-merge) over the same period, and cross-reference: if
  bypass rate is high and blocked-finding severity is mostly low/medium,
  that's the direct signature of this failure mode.
- Review the scanner's configuration file for a severity threshold
  setting (`--severity-threshold`, `failThreshold`, a SonarQube quality
  gate condition) and confirm whether one is actually set versus left at
  tool default (commonly "fail on any finding").
- Interview or survey the team on why bypasses happen -- confirm it's
  gate-friction-driven rather than a separate process problem (e.g.
  people bypassing because they don't understand the findings, which
  needs a different fix than threshold tuning).

## Fix
Configure the gate with a severity threshold that maps to an agreed risk
policy -- typically: block the build on critical/high-severity *new*
findings only, surface medium/low findings as visible but non-blocking
(a PR comment or dashboard entry, not a red build), and route
pre-existing findings to a tracked backlog outside the PR gate entirely
(see the baseline pattern used for initial SAST rollout). Pair this with
a narrow, audited exception process for the remaining blocking cases --
a time-boxed, ticket-linked override that a second person (security
lead or tech lead) approves, logged automatically, rather than a
frictionless personal bypass anyone can invoke silently. This keeps the
gate meaningful (it still blocks what actually matters) while removing
the pressure that drives people to disable it wholesale.

## Pitfalls
- Setting the threshold so loose that it never blocks anything is the
  opposite failure -- the gate becomes theater, giving false confidence
  in an audit/compliance narrative while catching nothing in practice;
  the threshold needs to be calibrated against real severity data, not
  just loosened until complaints stop.
- An exception process that's easier to use than fixing the actual
  finding becomes the default path for everything, recreating the
  original bypass problem in a more official-looking wrapper -- track
  and periodically review exception usage rate, not just whether one
  exists.
- Changing the threshold without re-baselining pre-existing findings
  first can still leave the gate blocking on old, already-accepted
  issues that happen to be high severity but were never actually going
  to be fixed soon -- combine threshold tuning with the baseline/backlog
  split, not as a substitute for it.

## Verify
After retuning, check CI history over the following few weeks for both
the bypass rate (should drop toward zero for the routine case) and
whether any high-severity new finding introduced in a test PR still
correctly fails the build -- confirm the gate blocks the deliberately
introduced critical issue while not blocking a PR that only touches
unrelated code with pre-existing lower-severity findings.
