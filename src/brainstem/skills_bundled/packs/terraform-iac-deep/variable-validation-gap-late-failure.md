---
name: variable-validation-gap-late-failure
description: An invalid Terraform variable value passes plan and apply successfully but causes a cloud API error or wrong resource mid-apply instead of failing fast.
triggers: ["terraform apply fails halfway through with API error", "bad input caused partial apply", "terraform variable validation missing", "terraform plan succeeded but apply failed", "invalid value not caught until apply"]
permissions: ["READ"]
---

## Symptom
`terraform plan` shows a seemingly reasonable diff and completes without
error, but `terraform apply` fails partway through with a cloud
provider API error (invalid parameter, value out of range, malformed
name) that traces back to a variable value that was wrong from the start
-- a typo'd region, an out-of-range CIDR block, a name with an
disallowed character -- leaving some resources created and others not,
because nothing validated the input before it reached the API.

## Likely causes
1. **The variable has no `validation` block at all**, so Terraform's
   type system only checks that the value is, say, a string -- it has no
   opinion on whether that string is a valid value for the specific
   resource attribute it flows into, deferring all real validation to
   whatever the provider/API happens to check.
2. **The invalid value flows through several layers of modules before
   reaching the resource that rejects it**, so the failure surfaces deep
   in the apply (often on a resource far from where the actual mistake
   was made), making the root cause harder to trace back to the original
   input.
3. **A validation block exists but only checks type/format shallowly**
   (e.g. confirms a string is non-empty) without checking
   provider-specific constraints (allowed character sets, length limits,
   valid enum values) that the actual API enforces, so it catches some
   bad inputs but not the one that actually occurred.
4. **The apply already created some resources successfully before
   reaching the one that rejects the bad value**, because Terraform
   applies resources in dependency-graph order and validation failures
   from the API only surface when that specific resource's turn comes up
   -- by which point other resources are already live and partially
   configured around the eventually-failing one.

## Diagnose
- Read the exact API error message from the failed apply -- cloud
  provider errors for invalid parameters usually name the specific field
  and constraint violated (e.g. "must match pattern," "must be between X
  and Y"), which points directly at the offending variable/attribute.
- Trace that attribute backward through the module call chain (grep for
  where it's assigned, from the failing resource up through each
  module's variable passthrough) to find the original source variable
  and where its value was set (a `tfvars` file, a CI variable, a default).
- Check `terraform state list` immediately after the failed apply to see
  exactly which resources were successfully created before the failure,
  since those now need to be accounted for (left as-is, or destroyed) as
  part of the fix rather than assumed to not exist.
- Check whether a `validation` block exists on the offending variable at
  all, and if so, what condition it actually checks versus what the API
  actually rejected -- this distinguishes "no validation" from
  "insufficient validation" as the specific gap.

## Fix
Add `validation` blocks on variables at the point closest to where a
human supplies the value (root module variables, and any reusable
module's own input variables), encoding the actual provider-side
constraints that matter (regex pattern for allowed names, numeric range
for ports/CIDR sizes, an explicit list for enum-like fields) so bad input
is rejected at `terraform plan`/`validate` time with a clear, custom
error message pointing at the actual problem -- instead of surfacing as
an opaque API error mid-apply, potentially after other resources already
changed. Layer validation at each module boundary the value crosses, not
just at the outermost root variable, so a module remains safe to reuse
even by a caller who doesn't read its internals closely.

## Pitfalls
- Writing an overly strict validation regex/range that rejects
  legitimate values the original author didn't anticipate (e.g. a valid
  but unusual resource name format) turns a helpful guardrail into a
  false-positive blocker; base validation constraints on the actual
  documented provider/API limits, not a guess, and test them against
  known-good edge-case values.
- Adding validation only after this specific failure occurred, on only
  the one variable that caused it, leaves every structurally similar
  variable elsewhere in the codebase equally exposed to the same class of
  late failure.

## Verify
After adding the validation block, run `terraform plan` (or `terraform
validate`) with the same invalid value that previously caused a mid-apply
failure, and confirm Terraform now rejects it immediately with the custom
validation error message -- before any resource is touched -- rather than
allowing the plan to proceed to apply.
