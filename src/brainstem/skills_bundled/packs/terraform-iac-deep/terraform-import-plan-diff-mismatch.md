---
name: terraform-import-plan-diff-mismatch
description: A terraform import brings an existing resource under management but the next plan shows unexpected changes because the config doesn't match the imported attributes.
triggers: ["terraform import shows plan changes", "terraform plan after import not clean", "imported resource wants to change on apply", "terraform import attribute mismatch", "plan not empty after import"]
permissions: ["READ"]
---

## Symptom
`terraform import` completes successfully (no error, resource added to
state), but the very next `terraform plan` shows changes -- sometimes
small attribute tweaks, sometimes a full replacement -- for the
just-imported resource, even though the intent of importing was to bring
it under management with zero drift.

## Likely causes
1. **The `.tf` configuration written for the resource doesn't match the
   real resource's actual current attributes** -- `terraform import`
   only populates state from the real infrastructure, it does not
   generate or validate matching HCL configuration, so any mismatch
   between hand-written config and reality shows up as a plan diff
   immediately after import.
2. **The resource has attributes with provider-side defaults that differ
   from Terraform's schema default** -- e.g. a cloud resource created
   years ago under an old API default that differs from what the current
   provider version treats as default when the attribute is left unset
   in config, so an "empty" config block doesn't actually match the
   imported reality.
3. **Computed/read-only attributes were captured into state at import
   time but the config references a different or conflicting value for
   a related settable attribute**, causing Terraform to reconcile toward
   the config's value on the next apply rather than preserving the
   imported one.
4. **The resource was imported using an identifier that maps to slightly
   different underlying attributes than expected** (e.g. importing by
   name when a similarly-named but distinct resource exists, or an ID
   format that includes an implicit region/account qualifier that wasn't
   accounted for), so the imported state is technically valid but for
   subtly the wrong real-world object or a stale snapshot of it.

## Diagnose
- Immediately after import, run `terraform plan` and read every proposed
  change line by line -- for each one, check whether it's an attribute
  the hand-written config set explicitly (config/reality mismatch) or one
  left unset (default mismatch).
- Run `terraform show -json` (or `terraform state show
  <resource.address>`) right after import to see the *actual* imported
  attribute values, and diff those manually against the `.tf` config
  block for the same resource, attribute by attribute, rather than
  relying on the plan summary alone for complex nested blocks.
- For attributes suspected to be provider-default mismatches, check the
  provider's resource documentation for the documented default and
  compare it against the imported state's value for that attribute when
  left unset in config.
- If the identifier used for import is ambiguous, independently verify
  the resource in the cloud console/CLI (outside Terraform) using the
  same ID to confirm it's the exact intended object before spending time
  reconciling a diff against the wrong resource.

## Fix
Treat the first post-import plan as the authoritative to-do list for
reconciling config with reality: for each diff line, update the `.tf`
configuration to explicitly set the attribute to the imported value
(rather than leaving it to an assumed default), working block by block
until `terraform plan` reports no changes. For resources with many
attributes, use `terraform show -json` output (or, on Terraform versions
that support it, `terraform plan -generate-config-out=generated.tf`
immediately as part of the import workflow) to generate a starting
configuration from the actual imported state instead of hand-writing it
from memory or documentation, then review and clean up the generated
config rather than trusting it blindly.

## Pitfalls
- Applying the post-import plan to "fix" the diff without checking
  *which side* is correct can silently change real infrastructure to
  match a config that was actually wrong -- e.g. reverting a legitimately
  custom setting on a production resource back to a naively-assumed
  default, causing a regression disguised as a state reconciliation.
- Treating a clean-looking `terraform plan` immediately after import as
  sufficient verification without checking `terraform state show` for
  the resource's full attribute set can miss a diff hidden inside a
  nested block or a list/map attribute that the plan output collapses or
  summarizes.

## Verify
After reconciling config to match imported reality (or vice versa, once
consciously decided), run `terraform plan` and confirm it reports the
resource with no proposed changes at all, then run it a second time after
an unrelated change elsewhere in the codebase to confirm the imported
resource remains stable and isn't quietly drifting back into a diff on
every subsequent plan.
