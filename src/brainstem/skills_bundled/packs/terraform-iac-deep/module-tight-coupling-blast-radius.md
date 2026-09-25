---
name: module-tight-coupling-blast-radius
description: A single monolithic root module makes every terraform plan slow, noisy, and risky because unrelated resources share one state file and one apply.
triggers: ["terraform plan takes forever", "terraform plan shows unrelated changes", "one state file for everything terraform", "splitting terraform state", "terraform apply blast radius too large"]
permissions: ["READ"]
---

## Symptom
`terraform plan` on the main infrastructure root module routinely takes
minutes, shows dozens of unrelated resources in the diff for a change
meant to touch one service, and any apply -- however small in intent --
carries the anxiety of "this touches everything," because the entire
organization's infrastructure lives in a single state file managed by
one root module.

## Likely causes
1. **The root module grew organically by always adding new resources to
   the existing `main.tf`/state** rather than deliberately deciding where
   a new resource's boundary should live, so unrelated systems (networking,
   individual services, shared IAM) accumulated into one graph over time.
2. **Cross-resource references were done via direct in-module Terraform
   references** (resource-to-resource within the same state) for
   convenience, creating implicit coupling that would require rework to
   untangle into separate state files with explicit data-sharing
   (outputs consumed via remote state or a registry) instead.
3. **No ownership boundary maps to the module boundary** -- multiple
   teams apply changes to the same root module/state, so any team's
   change forces a plan that includes every other team's resources too,
   and any lock contention or apply failure blocks unrelated teams.
4. **Fear of migration risk perpetuates the monolith** -- splitting state
   requires careful `terraform state mv`/`pull`/`push` work that feels
   riskier than just continuing to add to the existing module, so the
   coupling compounds further with each addition.

## Diagnose
- Time a `terraform plan` on the current root module and note both the
  wall-clock time and the number of resources in `terraform state list`
  -- a plan against thousands of resources for a change to a handful is
  a direct, measurable signal of the blast radius problem, not just a
  feeling.
- Review recent plan diffs (or `terraform show -json` outputs saved from
  past applies) for how many resources changed versus how many were
  merely evaluated/unchanged-but-included -- a high ratio of
  "refreshed but untouched" resources per intended change quantifies the
  coupling.
- Map resource groups to team/service ownership using tags or naming
  convention, then check whether those ownership boundaries cross into
  the same state file -- this identifies where a state split would
  actually reduce risk versus where resources are genuinely
  interdependent and belong together.
- Check for direct (non-remote-state) references between resources that
  conceptually belong to different systems (e.g. an application resource
  block directly referencing a networking resource's attribute in the
  same module) -- these are the specific couplings that block a clean
  split without rework.

## Fix
Split the monolithic root module along real ownership/change-frequency
boundaries (e.g. networking as its own state, shared IAM as its own
state, each service or team's resources as their own state), exposing
what other modules need via explicit `output` values consumed through
`terraform_remote_state` (or a proper state-sharing mechanism) rather
than direct in-graph references. Perform the split incrementally and
per-boundary using `terraform state mv` (or `state rm` from the old root
plus `import`/state file surgery into the new one) so each resource's
existing infrastructure is preserved without destroy/recreate, verifying
with a plan after each moved group before proceeding to the next,
rather than attempting one large simultaneous restructuring.

## Pitfalls
- Splitting state without first identifying and replacing direct
  in-module references with explicit remote-state outputs leaves
  dangling references that fail at plan time immediately after the
  split, or worse, silently resolve to stale/incorrect values.
- Over-splitting into too many tiny state files introduces its own cost
  -- more `terraform_remote_state` data sources to coordinate, more apply
  ordering to reason about manually, and more surface area for the
  cross-state versions of skills like module-output-shape-change and
  target-flag partial applies; split along real ownership/blast-radius
  boundaries, not arbitrarily.

## Verify
After completing a split for one boundary, run `terraform plan` in both
the new smaller root module and the original (now-reduced) one, and
confirm each reports the expected resource count in `terraform state
list` with zero unintended diff -- then time a `terraform plan` for a
typical single-resource change in the new smaller module and confirm it
completes measurably faster and with a narrower diff than the same class
of change did in the original monolith.
