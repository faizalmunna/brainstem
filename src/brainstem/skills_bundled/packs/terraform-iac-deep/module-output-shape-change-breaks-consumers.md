---
name: module-output-shape-change-breaks-consumers
description: A shared Terraform module's output changes type or shape and breaks every root module or consumer that references it across the codebase.
triggers: ["terraform module output breaking change", "module output type changed", "terraform invalid index on module output", "every environment broke after module update", "module refactor broke consumers"]
permissions: ["READ"]
---

## Symptom
After updating a shared module (e.g. changing an output from a single
string to a list, from a list to a map, or restructuring a nested object
attribute), every root module or environment that references
`module.x.some_output` starts failing with errors like "Invalid index,"
"this value does not have any attributes," or a plan that silently
produces wrong values -- and it's not confined to one environment, because
many consumers depended on the same output shape.

## Likely causes
1. **The module's output was changed to accommodate one new consumer's
   need** (e.g. supporting multiple subnets instead of one) without
   checking how many other root modules already consume that output in
   its old shape, since Terraform has no built-in cross-repo/cross-root
   consumer graph to warn the author.
2. **A provider or resource upgrade inside the module changed the
   underlying resource's exported attributes**, which the module's
   `output` block passes through directly, so the shape change originates
   from the provider, not from an intentional edit to the module's own
   code.
3. **The module was refactored from `count` to `for_each` (or vice
   versa)** internally, which changes whether an output is a list or a
   map keyed by string, even if the author didn't intend to change the
   module's public contract at all.
4. **No version pinning on the module source**, so consumers on `main`/
   unpinned tags picked up the breaking change immediately on their next
   `terraform init`, rather than opting in when ready.

## Diagnose
- Run `terraform plan` in each consuming root module and read the exact
  error: "Invalid index" or "Unsupported attribute" errors point directly
  at the output reference and old expected type; compare against
  `terraform providers schema -json` or the module's own `outputs.tf` to
  see the new declared type.
- Grep the codebase (across all repos/roots that use this module, not
  just the one that surfaced the error) for `module.<name>.<output>` to
  enumerate every consumer before making any further changes -- this
  finds silent breakage in modules that instantiate the value without
  erroring immediately (e.g. into a variable of a compatible-but-wrong
  type).
- Diff the module's `outputs.tf` between the previously-pinned ref/tag and
  the new one (`git diff <old-tag> <new-tag> -- outputs.tf`) to see
  exactly what changed in the output's expression, not just the resource
  changes.
- Check whether affected consumers pin the module source with an exact
  version (`?ref=v1.2.3`) or float on a branch/unpinned tag -- this
  determines whether the fix is "consumers need to bump intentionally" or
  "consumers already broke without any action on their part."

## Fix
Treat a shared module's outputs as a public API with semantic versioning:
bump the module's major version (and tag it accordingly) for any output
type/shape change, keep the old output name available with its old shape
in a deprecation window when feasible (e.g. add a new output like
`subnet_ids` alongside the old `subnet_id`, rather than repurposing
`subnet_id` itself), and require every consumer to pin an exact `ref` so
upgrading is an explicit, reviewed action per root module rather than an
implicit one on the next `init`. When a breaking change is unavoidable,
land it as a new major version tag and migrate consumers one at a time,
verifying each with a plan before moving to the next, rather than
force-pushing the breaking shape onto the existing tag.

## Pitfalls
- Fixing the immediate broken consumer by changing its code to match the
  new output shape, without bumping the module's version or auditing
  other consumers, leaves every other consumer on the same unpinned
  ref/branch still broken (or about to break on their next `init`).
- Renaming or reshaping an output and assuming `terraform state mv` or
  similar will smooth over the transition -- output shape changes are a
  config-and-consumer-code problem, not a state-addressing problem, and
  state operations don't fix a consumer expression that indexes into the
  wrong type.

## Verify
After pinning consumers to the new module version and updating their
references, run `terraform plan` in every previously-affected root module
and confirm each produces a clean plan with no type errors -- and
explicitly re-check any consumer that wasn't reported as broken initially
but references the same output, since silent type coercion can mask
breakage until apply time.
