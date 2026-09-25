---
name: production-approval-gate-bypassed-via-alternate-trigger
description: A production deployment reaches production without the intended human approval gate because it was triggered through a different, less-scrutinized path.
triggers: ["prod deploy skipped approval", "direct push deployed without review", "approval gate bypassed", "deployment happened without sign off", "hotfix branch skipped the approval step"]
permissions: ["READ"]
---

## Symptom
A change reaches production without ever passing through the intended
human approval step (a required reviewer sign-off, a change-advisory
gate, a manual "approve deploy" click) -- not because someone
deliberately overrode it, but because the deploy actually ran through a
different trigger path (a direct push to a deploy-tracking branch, a
manually-invoked pipeline job, a hotfix workflow) that was never wired to
require the same gate as the intended PR-merge-triggered path.

## Likely causes
1. **The approval gate is attached to one specific trigger event** (e.g.
   "on PR merged to main") **rather than to the deploy action itself** --
   any other event that can also produce a deploy (a direct push with
   force, a separate `workflow_dispatch`/manual-run trigger, a scheduled
   job, a webhook from another system) runs a pipeline that was authored
   before the approval requirement existed, or was authored separately
   and simply never had the gate added.
2. **A "hotfix" or "emergency" path was built with fewer checks by
   design**, intended for rare true emergencies, but with no compensating
   control (post-hoc review requirement, restricted access, alerting on
   use) -- so it becomes the path of least resistance for routine changes
   whenever the normal path feels slow, quietly becoming the common case
   rather than the rare exception it was designed for.
3. **Branch protection rules don't cover every path that can reach the
   deploy branch** -- required reviews/status checks are configured for
   pull requests, but the branch still permits direct pushes from users
   or service accounts with elevated permissions, or a separate
   long-lived branch/tag also triggers the same deploy pipeline without
   the same protection rules applied to it.
4. **The gate lives in a human process/runbook rather than being enforced
   by the pipeline system itself** -- "someone should approve before
   running this" is documented but not technically required by the
   pipeline (no blocking approval step in the pipeline definition), so
   it's trivially skippable by anyone who simply doesn't follow the
   runbook, whether by mistake or under time pressure.

## Diagnose
- Enumerate every way the deploy pipeline can actually be triggered
  (webhook events, manual dispatch, scheduled runs, branch pushes,
  tag pushes) by reading the full pipeline trigger configuration, not
  just the primary documented path -- most bypass incidents are found by
  discovering a trigger nobody was tracking as "a way to deploy."
- For each trigger found, check independently whether it enforces the
  same approval/gate requirement, rather than assuming gates configured
  on the main path apply universally.
- Check branch protection settings directly (required reviewers, required
  status checks, "restrict who can push," "include administrators") for
  every branch that can reach a deploy trigger, including any hotfix or
  release branches, not just the primary integration branch.
- Audit recent deploy history against approval records: for each
  production deploy in a given period, confirm a matching approval
  record exists, and flag every deploy that doesn't -- this surfaces
  actual bypass instances rather than theoretical ones.

## Fix
Move the approval requirement to be a property of the deploy action
itself, enforced by the pipeline/deployment system, rather than a
property of one specific trigger path: require the same approval gate
(a blocking manual-approval step in the pipeline, or a deployment
environment protection rule with required reviewers) regardless of what
triggered the pipeline run, so a direct push, a manual dispatch, and a
PR merge all funnel through the identical gate before anything reaches
production. Where an emergency/hotfix path must exist with reduced
friction, keep it technically distinct and rare by design -- restrict who
can invoke it, require a lightweight but still-enforced justification
field, and route every use of it to automatic post-hoc alerting/review
so its usage is visible and audited rather than silent.

## Pitfalls
- Adding an approval gate to the pipeline's "main" job definition but
  forgetting that the same YAML/config is reused (via a template or
  reusable workflow) by a second trigger that overrides or skips that
  particular step -- verify the gate is actually inherited, not just
  present in the file that's easiest to find.
- Making the emergency path so cumbersome to invoke "correctly" that
  people default to the easier bypass path instead, recreating the exact
  problem -- the legitimate emergency path needs to remain the path of
  least resistance among the *approved* options, even while being
  visibly audited.

## Verify
Attempt to trigger a production deploy through every non-primary path
identified during diagnosis (a manual workflow dispatch, a direct push to
the deploy branch in a test/staging clone of the setup) and confirm each
one is blocked pending the same approval as the primary PR-merge path,
with the block visible in the pipeline run's status rather than only
documented as a policy.
