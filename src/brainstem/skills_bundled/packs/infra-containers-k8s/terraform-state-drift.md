---
name: terraform-state-drift
description: Diagnose and resolve Terraform state drift (the real infrastructure no longer matches what Terraform's state file believes) before it causes a destructive plan/apply.
triggers: ["terraform state drift", "terraform plan wants to destroy", "terraform state out of sync", "manual change terraform", "terraform apply unexpected changes"]
permissions: ["READ", "DEPLOY"]
---

## Symptom
`terraform plan` shows unexpected changes -- resources it wants to
recreate, modify, or destroy that nobody intended to change -- because the
real infrastructure has diverged from what Terraform's state file
believes exists.

## Likely causes
1. **A manual change made directly** (via cloud console, CLI, or another
   tool) to a resource Terraform manages, bypassing Terraform entirely --
   the most common cause, especially under time pressure during an
   incident when someone fixes something by hand and forgets to reflect
   it in Terraform code.
2. **A resource was deleted outside Terraform** (manually, by a cleanup
   script, by the cloud provider due to a policy), so Terraform's state
   still references something that no longer exists.
3. **Another Terraform run (or a different tool/team) managing overlapping
   resources** without coordinated state, each believing it has sole
   ownership.
4. **A provider-side default or auto-generated value changing** (a cloud
   provider updating a resource's computed attribute) that Terraform then
   detects as drift on the next plan, even though nothing was intentionally
   changed.

## Diagnose
- Run `terraform plan` and read the diff carefully: does it show
  attribute-level changes (drift from a manual edit) or a full
  resource replacement/deletion (the resource may no longer exist, or
  its identifying attributes changed)?
- Use `terraform plan -refresh-only` to see specifically what's changed
  in real infrastructure versus state, without proposing any
  modification yet -- isolates drift detection from actual remediation.
- For a specific suspicious resource, check the cloud provider's audit
  log (CloudTrail, Cloud Audit Logs, Activity Log) around the time drift
  was introduced to identify what made the out-of-band change and when.

## Fix
- For a manual change that should be kept: update the Terraform
  configuration to match the new real-world state, then run
  `terraform apply` (or `terraform refresh`-equivalent via
  `-refresh-only` apply) so state and config converge on the *intended*
  final state, rather than letting the next apply silently revert the
  manual fix.
- For a manual change that should be reverted: run `terraform apply`
  normally so Terraform brings the resource back in line with the
  existing configuration -- but confirm this is actually desired first
  (see Pitfalls), since it will actively undo the manual change.
- For a resource deleted outside Terraform that should still exist,
  either `terraform apply` to recreate it (if recreation is safe/
  idempotent for that resource type) or `terraform import` if a
  replacement was already created manually and just needs to be brought
  under Terraform's management.
- For resources no longer meant to be managed by Terraform at all, use
  `terraform state rm` to remove them from state without destroying the
  real resource, then document that they're now unmanaged (or managed
  elsewhere).

## Pitfalls
- Running `terraform apply` reflexively to "fix" drift without reading
  the plan carefully can destroy a manual emergency fix that was
  load-bearing (e.g. a manually-scaled-up resource during an incident),
  causing a second incident.
- `terraform import` requires matching the resource's current real
  attributes closely enough that a subsequent plan doesn't immediately
  show a large diff -- import alone doesn't guarantee state and config
  actually agree; always run a plan immediately after import to confirm.
- Treating drift as purely a Terraform problem without addressing *why*
  manual changes happen (no fast enough Terraform-based path during
  incidents, unclear ownership) means the same drift recurs -- fixing the
  process gap matters as much as fixing the state.

## Verify
After remediation, run `terraform plan` again and confirm it reports no
changes ("infrastructure matches the configuration") -- a clean plan is
the concrete signal that state and reality have actually converged, not
just that the immediate error went away.
