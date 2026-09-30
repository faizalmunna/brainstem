---
name: provisioned-concurrency-cost-without-matching-traffic-pattern
description: Provisioned concurrency configured to eliminate cold starts is sized against a flat estimate, causing either continued throttling during spikes or wasted always-on cost.
triggers: ["provisioned concurrency not enough during spike", "lambda still cold starting with provisioned concurrency", "paying for idle provisioned concurrency", "provisioned concurrency cost too high"]
permissions: ["READ"]
---

## Symptom
A team enables provisioned concurrency to solve cold-start latency, and
one of two opposite problems shows up afterward: either the bill increases
noticeably because the provisioned instances sit mostly idle outside a
narrow daily peak (paying for warm capacity around the clock for a spiky,
bursty workload), or -- despite provisioned concurrency being enabled --
users still occasionally see cold-start-like latency spikes because actual
traffic exceeds the provisioned amount and the overflow falls back to
on-demand cold starts.

## Likely causes
1. **Provisioned concurrency was sized from a single peak-traffic estimate
   made once and never revisited**, so it either overshoots for a workload
   that's mostly quiet outside brief bursts (wasting cost) or undershoots
   as real traffic grows past the original estimate (letting overflow
   invocations cold-start anyway).
2. **The traffic pattern is bursty/spiky rather than steady**, and
   provisioned concurrency is a fixed floor, not an elastic ceiling --
   during a burst that exceeds the provisioned amount, the excess
   invocations scale via ordinary on-demand concurrency and pay the full
   cold-start cost, which can look like "provisioned concurrency isn't
   working" when it's actually working exactly as configured, just
   undersized for that specific burst.
3. **Application Auto Scaling for provisioned concurrency is either not
   configured or configured on a schedule/metric that doesn't match the
   actual traffic shape** (e.g., a fixed schedule that assumes business
   hours, for a workload that actually spikes based on external events at
   unpredictable times), so the provisioned amount doesn't track real
   demand even though autoscaling exists on paper.
4. **Provisioned concurrency is applied to a function version/alias that
   isn't the one actually receiving traffic** after a deployment (traffic
   shifted to a new version via an alias update, but provisioned
   concurrency wasn't re-associated with the new version), so it's paying
   for warm capacity that no invocation ever actually uses while the
   version actually serving traffic cold-starts normally.
5. **The team never measured whether cold starts were actually a
   user-facing problem for this specific function before paying for
   provisioned concurrency** -- for an internal or asynchronous function
   where occasional multi-hundred-millisecond cold starts don't affect
   any SLA, provisioned concurrency's ongoing cost may not be buying
   anything of actual value.

## Diagnose
- Pull the function's invocation volume over a full representative period
  (at least one full weekly cycle, to catch day-of-week patterns) and
  compare it against the flat provisioned concurrency number configured
  -- a workload with sharp peaks well above the provisioned floor and long
  troughs well below it is a mismatch in both directions simultaneously.
- Check the `ProvisionedConcurrencyUtilization` metric alongside
  `ProvisionedConcurrencySpilloverInvocations` -- sustained low
  utilization confirms over-provisioning cost waste, while nonzero
  spillover confirms under-provisioning is still causing on-demand cold
  starts despite the configuration existing.
- Confirm which specific function version/alias provisioned concurrency is
  actually attached to, and compare it against which version is actually
  receiving live traffic right now (via the alias's routing configuration)
  -- a mismatch after a recent deploy is a simple, common
  misconfiguration to rule out first.
- If Application Auto Scaling is configured, check its scaling schedule or
  target-tracking metric against actual traffic timestamps -- confirm the
  scaling schedule's assumed peak window actually lines up with when
  traffic really peaks, rather than assuming it does because it was
  configured once.
- For the underlying question of whether this is worth solving at all,
  check whether the function's cold starts actually correlate with a
  user-facing SLA violation or business complaint, versus being a metric
  that looks bad in isolation but has no measured downstream impact.

## Fix
Size provisioned concurrency from actual measured traffic patterns, not a
single estimate -- use Application Auto Scaling with a target-tracking
policy on utilization (so provisioned capacity tracks real demand
automatically) or a schedule derived from the function's actual observed
daily/weekly pattern, rather than a static number chosen once. For
workloads with genuinely unpredictable bursts that exceed any reasonable
provisioned floor, accept that some spillover to on-demand cold starts
will happen and size provisioned concurrency to cover the common case
economically, treating the rare burst overflow as an accepted tradeoff
rather than a bug to eliminate entirely. Always re-associate provisioned
concurrency with whatever version/alias is actually live immediately after
a deployment that shifts traffic, and prefer configuring it on a stable
alias rather than a specific version number so routing changes don't
silently orphan the provisioned capacity. Before adding provisioned
concurrency to a function at all, confirm cold-start latency is actually
causing a measurable user-facing or SLA problem for that specific
function, since not every function's cold start needs to be eliminated.

## Pitfalls
Setting provisioned concurrency very high "to be safe" after a single bad
incident overcorrects into paying continuously for capacity that's rarely
used, without actually fixing the underlying issue if that incident was
caused by a traffic pattern that can still exceed even the new higher
floor. Also, configuring autoscaling for provisioned concurrency but never
alerting on `ProvisionedConcurrencySpilloverInvocations` means
undersizing can persist silently for a long time, since the fallback to
on-demand cold starts doesn't cause hard failures, just degraded latency
that's easy to miss without an explicit metric watch.

## Verify
Compare `ProvisionedConcurrencyUtilization` and
`ProvisionedConcurrencySpilloverInvocations` over a full representative
traffic cycle after the resizing/autoscaling change -- utilization should
sit in a healthy working range (not pinned near zero, not constantly
saturated) and spillover invocations during normal traffic should drop
to the level the team has explicitly decided is acceptable, not simply
disappear as an unstated assumption.
