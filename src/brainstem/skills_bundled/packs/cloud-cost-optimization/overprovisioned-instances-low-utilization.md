---
name: overprovisioned-instances-low-utilization
description: A fleet of compute instances runs at consistently low CPU and memory utilization because instance sizes were chosen conservatively upfront and never revisited against real usage.
triggers: ["instances underutilized high cost", "overprovisioned compute rightsizing needed", "low cpu utilization high cloud bill", "instance size too large for actual load"]
permissions: ["READ"]
---

## Symptom

A review of compute utilization metrics across a fleet of instances
(VMs, containers, database instances) shows consistently low CPU and
memory usage -- often well under 20-30% at typical load -- while the
organization pays for instance sizes provisioned as if usage were much
higher, representing a large, ongoing, avoidable cost.

## Likely causes

- **Instance sizes were chosen conservatively during initial launch**
  (to avoid under-provisioning risk, or based on a rough guess rather
  than measured load) and were never revisited once real production
  usage patterns became known.
- **A previous traffic spike or anticipated growth that didn't
  materialize led to provisioning for peak-that-never-came**, and
  capacity was never scaled back down afterward.
- **Instance sizing decisions were made once per service at launch with
  no periodic rightsizing review process**, so sizing drifts further out
  of alignment with actual usage as the service's real traffic pattern
  evolves over time (in either direction).
- **A fear of destabilizing a working system discourages revisiting
  instance sizes** even when utilization data clearly suggests
  overprovisioning, since downsizing feels riskier than the status quo
  despite being financially significant.

## Diagnose

1. Pull CPU, memory, and (for network-bound workloads) network
   utilization metrics for the fleet over a representative period
   covering both typical and peak load, not just a snapshot.
2. Identify instances/services with sustained low utilization even during
   their own peak periods, which is the clearest rightsizing candidate
   (versus a service that's merely idle during off-hours but genuinely
   busy at its own peak).
3. Check whether utilization data reflects a genuinely stable pattern or
   an anticipated-but-unrealized growth scenario that might still
   materialize soon, which would argue for a longer observation window
   before downsizing.
4. Cross-reference against the cloud provider's own rightsizing
   recommendation tools (most major providers offer automated
   recommendations based on observed utilization) as a starting point,
   verified against the team's own understanding of the workload.

## Fix

Downsize instances to a size that comfortably accommodates observed peak
usage with reasonable headroom, based on actual measured utilization data
rather than the original conservative guess. Establish a periodic (e.g.
quarterly) rightsizing review as a standing practice, not a one-time
exercise, so sizing stays aligned with usage as it evolves. For
workloads with genuinely variable load, consider auto-scaling instead of
a single fixed size sized for peak, so capacity (and cost) tracks actual
demand rather than being fixed at a conservative ceiling at all times.

## Pitfalls

Don't downsize aggressively without a rollback plan or monitoring in
place to catch a genuine capacity problem quickly if the observed
utilization data missed a real peak scenario (a seasonal spike not
captured in the observation window, for instance) -- downsize in
measured steps with monitoring, not a single large cut based on limited
data. Also don't rightsize purely reactively after a cost review --
build it into a regular cadence so overprovisioning doesn't silently
reaccumulate.

## Verify

After downsizing, monitor utilization and application performance
(latency, error rate) over a subsequent period covering the workload's
own typical peak, confirming the smaller instance size still comfortably
handles real peak load with acceptable headroom, and confirm the
resulting cost reduction on the next billing cycle.
