---
name: wrong-workspace-applied-to-production
description: An apply intended for staging accidentally targets production because the wrong Terraform workspace was selected at apply time.
triggers: ["applied to production by accident", "terraform workspace select wrong environment", "ran terraform apply on prod instead of staging", "terraform workspace mix up", "accidentally destroyed production with terraform"]
permissions: ["READ"]
---

## Symptom
An engineer intends to run `terraform apply` against staging, but the
changes land in production instead -- discovered only after the apply
completes (or mid-apply) because production resources start changing,
even though the engineer's terminal history shows they typed a
"staging" command.

## Likely causes
1. **`terraform workspace show` was never checked before the apply** --
   Terraform workspaces are a persistent, silent piece of state tied to
   the working directory (`.terraform/environment`), so a workspace
   switched in a previous session (by the same engineer or a teammate
   sharing a machine/CI runner) stays selected until explicitly changed
   again, with no prompt at apply time confirming which one is active.
2. **The same backend/state is shared across environments distinguished
   only by workspace name**, and a copy-pasted command (`terraform
   workspace select prod` muscle memory, or a script parameterized
   incorrectly) selected the wrong one, with variable files
   (`prod.tfvars` vs `staging.tfvars`) passed inconsistently relative to
   the workspace actually selected.
3. **CI pipeline configuration derives the workspace from a branch name
   or pipeline variable that didn't update correctly** -- e.g. a
   pipeline triggered manually with a default/leftover environment
   variable, or a branch-to-workspace mapping that doesn't cover a new
   branch name and falls back to a default workspace that happens to be
   production.
4. **Workspaces are used at all for environment separation**, which
   Terraform's own documentation cautions against for meaningfully
   different environments -- workspaces share the same backend
   configuration and provider credentials by design, so there's no
   structural barrier (different state file, different credentials)
   preventing a mis-selected workspace from reaching production.

## Diagnose
- Immediately run `terraform workspace show` in the exact directory and
  shell session where the apply happened, and cross-reference against
  shell/CI history to reconstruct which workspace was actually active at
  the moment of `apply` (not what the engineer intended).
- Check the CI job logs for the literal `terraform workspace select` (or
  `-var-file`) command that ran, and compare against the pipeline
  variable or branch name that should have determined it -- look
  specifically for a fallback/default value being silently used.
- Review the state backend's versioning (S3 object versions, Terraform
  Cloud state history) for the production workspace to see the exact
  diff the mistaken apply introduced, scoping the blast radius precisely
  rather than assuming based on the plan output alone.
- Check whether staging and production actually share one backend
  configuration with only the workspace name differing, versus fully
  separate backend configs/state files -- this determines whether the
  root cause is "wrong workspace selected" or "the architecture makes
  this mistake structurally easy."

## Fix
Prefer separate state backends (and ideally separate cloud
accounts/projects with separate credentials) per environment over
Terraform workspaces for meaningfully different environments like
staging versus production -- this turns "wrong workspace selected" into
"wrong directory/credentials entirely," which is far harder to do by
accident and often blocked outright by credential scoping. Where
workspaces are already in use and a full split isn't immediately
feasible, add a hard guard: a `precondition` check or a wrapper script
that refuses to apply unless the selected workspace name matches an
expected value passed explicitly (not defaulted), and require CI
pipelines to print and assert the active workspace name as an explicit
step before any apply, failing loudly rather than proceeding on an
unverified default.

## Pitfalls
- Adding a confirmation prompt ("Are you sure you want to apply to
  prod?") as the only safeguard is easy to click through on autopilot,
  especially under the same time pressure that caused the original
  mistake -- pair prompts with a structural check (workspace name
  assertion, separate credentials) rather than relying on human attention
  alone.
- Migrating away from workspaces to separate backends without carefully
  migrating each environment's existing state (via `terraform state
  mv`/`pull`/`push` per environment) risks losing state entirely for one
  environment mid-migration; treat the migration itself as a change that
  needs its own plan and verification.

## Verify
After applying the guard (explicit workspace assertion or full backend
separation), attempt to reproduce the mistake deliberately in a
non-production test: try to run the staging-intended command while
production's workspace/credentials are active, and confirm the guard
rejects the operation with a clear error before any resource changes,
rather than silently proceeding.
