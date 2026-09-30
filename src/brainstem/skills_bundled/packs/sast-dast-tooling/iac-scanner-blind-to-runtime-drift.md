---
name: iac-scanner-blind-to-runtime-drift
description: Infrastructure-as-code security scans pass cleanly while the deployed environment is actually misconfigured because the running infra has drifted from the scanned templates.
triggers: ["checkov passed but the s3 bucket is public", "tfsec clean but resource misconfigured in console", "iac scan doesnt match production config", "terraform plan clean but real infra insecure", "infra drifted from what we scanned"]
permissions: ["READ"]
---

## Symptom
An IaC-focused SAST-style scanner (Checkov, tfsec, Terrascan, KICS)
runs against Terraform/CloudFormation source and reports a clean pass on
every merge, giving the team confidence their infrastructure is
securely configured -- yet a manual cloud console audit or an actual
DAST/cloud-posture finding reveals a real resource (an S3 bucket, a
security group, an IAM role) is misconfigured in a way the IaC scan
should have caught, because the deployed resource no longer matches what
the scanned templates describe.

## Likely causes
1. **Manual out-of-band changes were made directly in the cloud
   console/CLI** after deployment (a common emergency-fix or
   "just this once" habit) that never got reflected back into the IaC
   source, so the scanner is validating a template that no longer
   describes reality.
2. **The IaC scan only runs on the templates at PR time, not against
   the actual deployed state** -- there's no drift-detection step
   (`terraform plan` against real state, a cloud-posture tool comparing
   live config to source) closing the loop between "source passed scan"
   and "deployed resource matches source."
3. **The scanned module/resource isn't the one actually provisioning the
   live resource** -- a resource was originally created by an older
   module version or a different tool (ClickOps, a different IaC repo,
   a legacy CloudFormation stack) and later "adopted" into Terraform
   state or left unmanaged, so current scans never actually cover it.
4. **Scan scope excludes the environment/workspace that diverged** --
   the CI pipeline scans the `main` branch's templates but a
   hotfix/manual change happened in a specific environment's workspace
   or tfvars that isn't part of the scanned path, common in multi-
   environment setups with per-environment overrides.

## Diagnose
- Run `terraform plan` (or the equivalent for the IaC tool in use)
  against the actual deployed state for the affected resource and check
  whether it reports a diff -- a non-empty plan on a resource believed
  to be "just deployed from clean-scanned source" is the direct
  signature of drift.
- Check the resource's cloud-provider change history/CloudTrail
  (or equivalent audit log) for modifications made outside the IaC
  pipeline's execution identity -- console/CLI changes show a different
  principal/access pattern than CI-driven deploys.
- Confirm which IaC scan job actually covers the environment/workspace
  where the misconfigured resource lives -- check the CI config's path
  filters and branch/workspace targeting against where the divergent
  resource is actually defined.
- Check whether the resource is under Terraform/CloudFormation
  management at all (`terraform state list` or stack resource list) --
  a resource created out-of-band and never imported into state is
  invisible to both the scan and drift detection entirely.

## Fix
Close the loop between static IaC scanning and deployed reality with a
scheduled or triggered drift-detection step -- run `terraform plan`
(or the cloud-native equivalent) on a schedule against live state and
alert on any non-empty diff, treating drift itself as a finding to
triage, not just a scan-time template check. Where manual out-of-band
changes are sometimes operationally necessary (a genuine break-glass
emergency fix), require the fix to be backported into IaC source in a
fast-follow PR rather than left as permanent drift, and restrict direct
console/CLI write access to production resources for routine changes so
IaC remains the actual source of truth. For resources not currently
under IaC management, prioritize importing them (`terraform import` or
equivalent) so they enter both the scan's and drift-detection's scope
rather than remaining permanently invisible.

## Pitfalls
- Treating a clean IaC scan as equivalent to "the infrastructure is
  secure" conflates source-code correctness with deployed-state
  correctness -- they are only equivalent when drift is actively
  monitored, not by default.
- Locking down console access so tightly that legitimate incident
  response is blocked pushes emergency fixes through slower, riskier
  workarounds -- pair restricted routine access with a documented,
  audited break-glass path rather than a blanket lockout.
- Importing a drifted resource into IaC state without first reconciling
  the source template to match its *current* (possibly insecure)
  configuration can cause the next `apply` to silently "fix" it in a way
  that causes an unplanned production change -- review the diff before
  applying after any import.

## Verify
After adding drift detection, deliberately make an out-of-band console
change to a non-critical test resource and confirm the drift-detection
job flags it within its scheduled interval, then remediate via IaC and
confirm the next scheduled run reports a clean (empty) plan again,
proving the loop between source, scan, and live state is actually
closed.
