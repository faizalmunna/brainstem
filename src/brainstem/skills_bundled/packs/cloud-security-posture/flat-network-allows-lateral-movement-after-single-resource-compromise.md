---
name: flat-network-allows-lateral-movement-after-single-resource-compromise
description: An incident review finds a single compromised instance could reach many unrelated internal resources because network segmentation between workloads was never enforced.
triggers: ["attacker moved laterally from one instance to everything else", "why could that compromised pod reach the database directly", "flat network no segmentation between environments", "one compromised host had a path to production data"]
permissions: ["READ"]
---

## Symptom

A post-incident review of a single compromised VM, container, or
function finds the blast radius was far larger than the compromised
workload's actual job -- the attacker pivoted from a low-value,
internet-facing resource straight to sensitive internal systems
(databases, internal admin tools, other unrelated services) because
there was no network-level boundary stopping that traffic. Every
workload in the account/VPC could reach every other workload by default.

## Likely causes

- **All workloads were placed in a single flat VPC/virtual network with
  broad internal security-group/NSG rules** ("allow all traffic from
  within the VPC") set up early for convenience, since segmenting
  traffic requires upfront design work that gets deferred when the
  priority is getting things running.
- **Environments (dev/staging/production) or trust tiers
  (public-facing/internal/data) were never separated into distinct
  network boundaries (subnets, VPCs, projects)**, so a lower-trust
  environment sits on the same reachable network as the highest-value
  systems.
- **Segmentation exists on paper/diagram but wasn't actually implemented
  in the live security-group/firewall/NSG rules** -- an architecture
  document shows tiers, but the actual rules allow broad internal
  traffic because implementing the stricter rules broke something during
  initial rollout and the broad rule was left in place "temporarily."
- **New services are added to the network without anyone re-evaluating
  whether the existing broad internal-allow rules still make sense**,
  so segmentation debt compounds as the environment grows past its
  original, smaller scope.

## Diagnose

1. Map current network reachability directly from security-group/NSG/
   firewall rule configurations (not the architecture diagram) --
   identify which resource groups can currently reach which other
   resource groups, focusing on whether internet-facing workloads can
   reach data-tier or admin-tier resources directly.
2. Cross-reference actual observed traffic (VPC Flow Logs / NSG flow
   logs) between resource groups against what reachability rules
   currently allow, to distinguish rules that are actively relied upon
   from broad rules nothing is actually using.
3. Identify the trust-tier boundary that was crossed in the incident
   specifically (which rule allowed the compromised resource to reach
   the sensitive target) and check whether that rule was a deliberate,
   documented exception or an artifact of a broad "allow internal" rule.
4. Check whether environment separation (dev/staging/prod) maps to
   actual distinct network boundaries or whether they merely sit in
   different naming conventions within the same reachable network.

## Fix

Segment the network by trust tier (public-facing / internal application
/ data) and by environment, using distinct subnets, security groups, or
separate VPCs/virtual networks with explicit, narrow allow rules between
tiers instead of one broad internal-allow rule -- traffic from the
public tier to the data tier should only be permitted through the
specific application tier resources that legitimately need it, not
directly. Adopt a default-deny posture for east-west traffic and add
allow rules only for the specific, documented service-to-service
communication paths that traffic analysis confirms are actually needed,
using the flow-log analysis from diagnosis as the basis for what to
allow rather than guessing. Roll this out incrementally starting with
the highest-value trust boundary (public-facing to data-tier) rather
than attempting a full redesign at once.

## Pitfalls

Don't implement default-deny segmentation by immediately blocking
everything not already observed in a short flow-log sample -- traffic
patterns that occur only periodically (batch jobs, monthly reports,
failover paths) won't show up in a short observation window and will
break unexpectedly later; validate against a longer window or explicit
architecture knowledge before finalizing deny rules.

## Verify

From a test resource in the public/internet-facing tier, attempt direct
network connections to data-tier resources and confirm they're blocked
except through the specific intended application-tier path. Run the
segmentation change against a full cycle of the environment's periodic
workloads (batch jobs, scheduled maintenance) and confirm no legitimate
traffic was broken before considering the rollout complete.
