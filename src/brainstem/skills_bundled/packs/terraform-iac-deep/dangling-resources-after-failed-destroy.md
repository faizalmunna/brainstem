---
name: dangling-resources-after-failed-destroy
description: A terraform destroy or resource removal fails partway through, leaving real cloud resources still running but no longer tracked in state.
triggers: ["terraform destroy failed partway", "resources still exist after terraform destroy", "removed from state but still running", "terraform destroy timeout left resources", "orphaned cloud resources after terraform"]
permissions: ["READ"]
---

## Symptom
A `terraform destroy` (or a plan that removes resources from
configuration) reports an error partway through -- a timeout, a dependency
violation from the cloud API, a permissions error -- and afterward some
resources are gone from `terraform state list` while the actual cloud
resources are still running and billing, or conversely some resources
remain in state as "to be destroyed" indefinitely because every attempt
fails at the same point.

## Likely causes
1. **A cloud-side dependency prevents deletion in the order Terraform
   attempts it** -- e.g. a resource still has an attached
   dependent (a load balancer still referencing a target group, a VPC
   still containing resources Terraform doesn't manage) that the API
   refuses to delete out of order, causing that step to fail while
   resources destroyed earlier in the same run are already gone.
2. **A resource was already deleted out-of-band before the destroy ran**
   (manually, by a cleanup script, by the provider), so Terraform's
   delete API call fails with a "not found" error -- but depending on the
   provider's error handling, this can either be gracefully treated as
   already-deleted or hard-fail the whole run, leaving state
   inconsistent either way.
3. **A destroy timeout is too short for a genuinely slow-to-delete
   resource** (some managed database or cluster deletions take much
   longer than a resource's default timeout), so Terraform gives up and
   reports failure while the actual deletion is still in progress on the
   provider side, and re-running immediately races the in-progress
   deletion.
4. **Insufficient IAM/permissions for the delete operation specifically**
   (common when create/update permissions were granted but delete was
   forgotten in a least-privilege policy), causing every destroy attempt
   for that resource type to fail identically until permissions are
   fixed, while other resources in the same run may have already been
   removed.

## Diagnose
- Read the exact error from the failed destroy -- it typically names the
  specific resource and API-level reason (dependency violation, not
  found, timeout, access denied), which narrows the cause immediately
  rather than requiring speculation.
- Run `terraform state list` right after the failure and compare against
  what actually still exists in the cloud provider's console/CLI for the
  same resources, to build an accurate picture of the *actual* mismatch
  (state says gone but resource exists, or state says present but
  resource is already gone) rather than assuming state is authoritative.
- For dependency-violation errors, check the cloud provider's own
  dependency error message for which specific other resource is blocking
  deletion, and check whether that blocking resource is managed by this
  same Terraform config, a different one, or created manually outside
  Terraform entirely.
- For suspected timeout issues, check the resource's actual deletion
  status directly via the provider's console/CLI (not just Terraform)
  to see if it's still in a "deleting" state server-side, before
  retrying `terraform destroy` and risking a race with the in-progress
  operation.

## Fix
Reconcile state and reality explicitly before retrying blindly: for
resources genuinely still running that state no longer tracks, either
re-`import` them (if they should still be destroyed via Terraform) or
document them as manually-owned going forward; for resources already
gone that state still lists, use `terraform state rm` to clear the stale
entry so a retry doesn't fail trying to delete something nonexistent.
For dependency-ordering failures, adjust the configuration's
`depends_on`/lifecycle relationships (or resolve the out-of-band
dependency manually) so the destroy order matches what the API actually
requires, and for slow-deleting resources, set an explicit longer
`timeouts { delete = "..." }` block on that resource rather than relying
on the provider's default.

## Pitfalls
- Immediately retrying `terraform destroy` after a timeout-related
  failure without checking the resource's actual server-side status can
  race an in-progress deletion, sometimes triggering provider-side errors
  about conflicting concurrent operations that are harder to diagnose
  than the original timeout.
- Using `terraform state rm` to make a stuck destroy "succeed" without
  confirming the real resource is actually gone (or explicitly intended
  to be orphaned) creates a silently unmanaged, still-billing resource
  that no longer appears anywhere in Terraform's view of the world.

## Verify
After reconciling state and retrying, run `terraform destroy` (or
`terraform plan` if only partial removal was intended) to completion and
confirm both that Terraform reports success and that the cloud
provider's own console/CLI independently confirms the targeted resources
no longer exist -- checking the provider directly, not just Terraform's
exit code, since Terraform can only report on what it's aware of.
