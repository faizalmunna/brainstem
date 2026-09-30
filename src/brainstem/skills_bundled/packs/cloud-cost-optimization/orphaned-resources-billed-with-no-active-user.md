---
name: orphaned-resources-billed-with-no-active-user
description: Cloud spend includes a meaningful share of resources still running and billed even though no application or team is actually using them anymore.
triggers: ["cloud bill has orphaned resources", "unused ec2 instances still billing", "forgotten cloud resources cost", "orphaned volumes and ips still charged"]
permissions: ["READ"]
---

## Symptom

A cost review or a billing anomaly investigation finds a meaningful
fraction of cloud spend attributable to resources (compute instances,
storage volumes, load balancers, reserved IPs, managed database
instances) that no application or team is actively using -- often
discovered because nobody can immediately explain what a specific
resource is for when asked.

## Likely causes

- **A resource was provisioned for a project, experiment, or migration
  that finished or was abandoned**, and cleanup was never done because
  decommissioning isn't tied to any deletion trigger -- deprovisioning
  requires someone to remember to do it, and nobody did.
- **A resource (a disk volume, a snapshot, an elastic IP) is decoupled
  from the compute instance it was originally attached to**, and got left
  behind when that instance was terminated, continuing to be billed
  independently and easy to miss since it's not visually associated with
  anything obviously "in use."
- **No consistent tagging/ownership convention exists**, so even when a
  resource is noticed, nobody can quickly determine who owns it or
  whether it's safe to delete, leading to it being left alone indefinitely
  out of caution.
- **Auto-scaling or CI/CD pipeline bugs create resources that are never
  cleaned up** (a test environment provisioned per PR that isn't torn
  down when the PR closes, a scaling event that doesn't scale back down
  due to a stuck process).

## Diagnose

1. Use the cloud provider's cost/resource inventory tools (cost
   explorer, resource inventory/tagging reports) to list resources by
   type and age, specifically looking for old resources with no recent
   activity metrics (no CPU utilization, no network traffic, no query
   volume).
2. Cross-reference resource ownership tags (or lack thereof) against
   current team/project rosters to identify resources with no
   identifiable current owner.
3. Check for detached storage volumes, unattached elastic IPs, and
   orphaned load balancers specifically, since these are common
   "invisible" cost categories that don't show up as obviously as a
   running compute instance would.
4. Audit CI/CD pipeline and auto-scaling configurations for any
   resource-creation step that doesn't have a corresponding, reliably
   triggered cleanup step.

## Fix

Establish a mandatory tagging convention (owner, project, environment,
expiration/review date) enforced at resource creation (via policy, not
just documentation), making ownership and purpose immediately visible for
any resource going forward. Set up automated or scheduled review of
untagged or long-idle resources with a defined process for confirming
whether they're safe to delete. Fix CI/CD pipelines and auto-scaling
configurations to reliably tear down temporary resources, treating a
missing cleanup step as a bug, not a minor inconvenience. For genuinely
orphaned resources found during a review, decommission them after
confirming with any plausible remaining stakeholders.

## Pitfalls

Don't delete an unrecognized resource immediately without any
verification just because it looks unused -- a resource with low
visible activity might still be load-bearing for something infrequent
(a disaster-recovery standby, a rarely-triggered batch job) that isn't
obvious from surface-level activity metrics; use a hold/quarantine period
(disable, don't delete, then delete after a confirmation window) rather
than immediate deletion for anything not conclusively verified as safe.

## Verify

Re-run the resource inventory/cost analysis after implementing tagging
and cleanup processes and confirm a measurable reduction in
untagged/unowned resources and their associated cost. Confirm the CI/CD
and auto-scaling fixes actually result in resources being torn down as
expected by observing several real cycles (PR close, scale-down event)
rather than just reviewing the configuration change.
