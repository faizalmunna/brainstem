---
name: data-egress-cost-spike-cross-region-traffic
description: A cloud bill shows a large, unexpected data-egress or cross-region-transfer cost line item that wasn't accounted for when the architecture was designed.
triggers: ["data egress cost unexpected", "cross region transfer cost spike", "cloud bandwidth bill too high", "inter az traffic cost"]
permissions: ["READ"]
---

## Symptom

A cloud bill's data transfer/egress line item is significantly larger
than expected, sometimes rivaling or exceeding compute costs, and the
architecture wasn't originally designed with data transfer cost as an
explicit consideration -- the specific traffic pattern responsible isn't
immediately obvious from the bill alone.

## Likely causes

- **Services that communicate frequently are deployed across different
  availability zones or regions** without considering that inter-AZ and
  especially inter-region traffic is billed, sometimes substantially,
  unlike same-AZ traffic which is often free or much cheaper.
- **A data pipeline or replication process regularly transfers large
  volumes of data out of the cloud provider (or across regions) as part
  of its normal, expected operation**, but the cost of that recurring
  transfer was never explicitly modeled when the pipeline was designed.
- **A misconfigured service (a backup job, a logging pipeline) sends data
  to an unintended destination** (the wrong region, an external endpoint
  instead of an internal one) far more frequently or in far larger volume
  than intended.
- **Client-facing content (large media files, API responses) is served
  directly from origin storage/compute without a CDN**, incurring
  egress cost on every request that a properly configured CDN would have
  cached and served more cheaply.

## Diagnose

1. Use the cloud provider's cost breakdown/billing detail specifically
   for data transfer, broken down by source/destination service, region,
   and transfer type (same-AZ, cross-AZ, cross-region, internet egress)
   to identify which specific traffic pattern dominates the cost.
2. Check architecture diagrams/deployment configuration for services that
   communicate frequently but are placed in different AZs/regions,
   correlating with the highest-cost transfer categories identified.
3. Check data pipeline/replication job configurations for their actual
   transfer volume and frequency against what was originally
   estimated/budgeted, if any estimate was made at all.
4. Check for any obviously misconfigured destination in backup/logging/
   replication configurations that might be sending data somewhere
   unintended.

## Fix

Co-locate frequently-communicating services within the same
availability zone (or region, at minimum) where architecturally
feasible, accepting the tradeoff against multi-AZ resilience where cost
genuinely outweighs the marginal resilience benefit for a given
component. Introduce a CDN for client-facing content to reduce repeated
origin egress. For necessary cross-region data pipelines, evaluate
whether transfer volume can be reduced (compression, transferring only
deltas/changes instead of full datasets, aggregating before transfer)
rather than accepting the full cost as fixed. Fix any misconfigured
destination causing unintended transfer.

## Pitfalls

Don't co-locate services in a single AZ purely for cost savings without
considering the resilience tradeoff for genuinely critical, high-
availability-requiring components -- the right balance depends on the
specific service's actual availability requirements, not a blanket
policy applied everywhere. Also don't assume every data-transfer cost is
avoidable -- some cross-region transfer is a legitimate, necessary cost
of a multi-region architecture's benefits (disaster recovery, latency for
geographically distributed users); the goal is eliminating unintentional
or unnecessarily large transfer, not all transfer.

## Verify

After making architectural changes (co-location, CDN introduction,
pipeline optimization), monitor the data transfer cost line item over the
following billing cycle(s) and confirm a measurable reduction consistent
with the specific changes made, while confirming application
functionality and acceptable latency/availability are maintained.
