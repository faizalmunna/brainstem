---
name: target-flag-partial-apply-dependency-skip
description: Applying with terraform apply -target bypasses the full dependency graph and leaves downstream resources out of sync with the targeted change.
triggers: ["terraform apply -target left things broken", "terraform -target caused drift", "partial apply terraform dependency graph", "terraform target flag side effects", "downstream resources not updated after targeted apply"]
permissions: ["READ"]
---

## Symptom
After running `terraform apply -target=<specific_resource>` to push
through an urgent, narrow change, a subsequent full `terraform plan`
(without `-target`) shows a batch of unrelated-looking changes to *other*
resources -- ones that depend on the targeted resource but weren't
updated when it was, because the targeted apply intentionally skipped the
rest of the dependency graph.

## Likely causes
1. **`-target` explicitly instructs Terraform to only consider the named
   resource (and its dependencies), not its dependents** -- resources
   that reference the targeted resource's output (e.g. an instance
   referencing a security group ID that just changed) are not
   recalculated or updated by a targeted apply, so they silently become
   stale relative to the new state of the resource they depend on.
2. **`-target` was used under time pressure (an incident, an urgent
   fix) as a way to avoid reviewing a large, unrelated plan diff**,
   without a deliberate follow-up plan to run a full apply afterward to
   reconcile everything else -- the partial apply was meant to be
   temporary but the full reconciliation step got skipped or forgotten.
3. **Repeated use of `-target` becomes a habit for "speeding up" applies
   in a large state**, rather than an exceptional escape hatch, so the
   codebase accumulates multiple rounds of partial, unreconciled applies
   whose combined effect on dependents is no longer easy to reason about
   from any single plan.
4. **A `-target` apply changed something that dependents only pick up via
   a `terraform_remote_state` data source or a separate root module**,
   not a direct in-graph reference -- so even a subsequent full apply of
   the *same* root module won't catch the inconsistency; a different root
   module needs its own plan/apply to notice the upstream change at all.

## Diagnose
- Run `terraform plan` without any `-target` flag immediately after a
  targeted apply and read the full diff -- any changes proposed for
  resources *other* than the one just targeted are very likely
  downstream reconciliation that the targeted apply deliberately
  deferred, not new unrelated drift.
- Use `terraform graph` (or `terraform plan -out=tfplan &&
  terraform show -json tfplan` inspecting `resource_changes`) to identify
  which resources declare a dependency (directly or via
  `depends_on`/implicit reference) on the resource that was targeted,
  building an explicit list of what should be checked for staleness.
- Check shell/CI history for how many `-target` applies have run against
  this state recently and in what order -- multiple stacked targeted
  applies without an intervening full apply compound the reconciliation
  gap and make it harder to reason about from the current plan alone.
- For cross-root-module dependencies via `terraform_remote_state`, check
  each consuming root module's own `terraform plan` separately -- a clean
  plan in the root module that was targeted says nothing about
  consumers in other root modules/state files.

## Fix
Treat `-target` strictly as a temporary, narrow escape hatch for a
specific emergency (e.g. unblocking a stuck apply on one resource) and
always follow it with a full, untargeted `terraform plan`/`apply` as soon
as it's safe to do so, reviewing that follow-up plan specifically for the
reconciliation changes the targeted apply deferred. For routine large
applies that are slow or produce noisy diffs, address the root cause
instead of reaching for `-target` as standard practice -- split an
overly large root module into smaller ones with well-defined boundaries
(state per bounded context) so that ordinary applies are naturally
narrower in scope without bypassing the dependency graph.

## Pitfalls
- Chaining multiple `-target` flags to approximate "a full apply but
  skip this one flaky resource" changes the effective apply order and
  scope in ways that are easy to get subtly wrong, and still leaves
  everything outside the targeted set unreconciled -- it doesn't compose
  safely the way a full apply does.
- Treating a clean `-target` apply's own output as proof nothing else
  needs attention -- Terraform's targeted-apply output only reports on
  what it processed, so it gives no positive signal about the state of
  everything it skipped.

## Verify
Run a full `terraform plan` with no `-target` flag and confirm it reports
no pending changes -- a clean, untargeted plan is the concrete evidence
that every dependent resource has caught up with the targeted change,
not just that the original urgent fix succeeded.
