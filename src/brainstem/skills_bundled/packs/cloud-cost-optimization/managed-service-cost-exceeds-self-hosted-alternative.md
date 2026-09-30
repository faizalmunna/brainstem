---
name: managed-service-cost-exceeds-self-hosted-alternative
description: A managed cloud service's cost grows disproportionately to its actual value at scale, well beyond what a self-hosted or alternative approach would cost for the same workload.
triggers: ["managed service too expensive at scale", "cloud managed database cost vs self hosted", "serverless cost exceeds expectations at scale", "managed service cost doesn't scale linearly"]
permissions: ["READ"]
---

## Symptom

A managed cloud service (a managed database, a serverless compute
platform, a managed queue/streaming service) that was cost-effective and
low-maintenance at smaller scale now represents a disproportionately
large cost line item as usage has grown, to the point that a cost
comparison against self-hosting the equivalent capability (or using a
different service) shows a substantial, sustained gap.

## Likely causes

- **The service's pricing model (per-request, per-GB-processed, per-RU)
  scales linearly or worse with usage**, while the underlying
  infrastructure cost of self-hosting the equivalent capability often has
  economies of scale that don't pass through to the managed service's
  per-unit price at higher volumes.
- **The workload's usage pattern changed from what the managed service's
  pricing model was well-suited for** (bursty, low-baseline usage where
  serverless/pay-per-use shines) to a different pattern (sustained,
  high, predictable usage where a provisioned/reserved or self-hosted
  approach is typically more cost-effective).
- **The original decision to use the managed service optimized for
  reduced operational burden at a time when the team was small/early-
  stage**, and that tradeoff was never revisited as the team grew enough
  to reasonably absorb more operational responsibility in exchange for
  lower cost.
- **No periodic cost-versus-alternatives analysis exists** for
  significant infrastructure spend categories, so a growing cost gap
  between the managed service and alternatives isn't noticed until it
  becomes large enough to prompt an ad hoc investigation.

## Diagnose

1. Break down the managed service's actual cost by its pricing dimensions
   (requests, data processed, provisioned capacity) and model how that
   cost scales as usage continues to grow, to understand the trajectory,
   not just the current number.
2. Estimate the cost of a realistic alternative (self-hosting the
   equivalent open-source software on standard compute, or a different
   managed service with a better-fitting pricing model for this specific
   usage pattern) using the same current and projected usage.
3. Factor in the genuine additional operational cost of the alternative
   (engineering time for setup, maintenance, on-call burden) as a real
   cost, not just comparing raw infrastructure pricing.
4. Check whether the workload's actual usage pattern (bursty vs.
   sustained) still matches what the current service's pricing model was
   chosen for, or whether it's shifted.

## Fix

Where the total-cost comparison (including realistic operational
overhead, not just sticker price) clearly favors an alternative and the
team has the operational capacity to take it on, migrate to the more
cost-effective option -- whether that's self-hosting, a differently-
priced managed service, or a hybrid approach. Where operational capacity
genuinely doesn't support the switch, at minimum negotiate committed-use
discounts with the current provider if usage is now large and predictable
enough to qualify, since large-scale usage is exactly where such
discounts have the most leverage. Build periodic cost-vs-alternatives
review into planning for the organization's largest infrastructure cost
categories specifically, since this is where the absolute savings
potential is largest.

## Pitfalls

Don't decide to migrate away from a managed service based purely on raw
infrastructure cost comparison without honestly accounting for the
operational burden the managed service was originally adopted to avoid
-- a migration that saves money on the cloud bill but creates a
maintenance burden the team can't actually sustain is a net loss, not a
win. Weigh the full cost, including risk and engineering time.

## Verify

If a migration is undertaken, track actual total cost (infrastructure
plus a reasonable estimate of ongoing operational engineering time) for
several months post-migration and compare against the pre-migration
managed-service cost to confirm the anticipated savings materialized in
practice, not just in the original projection.
