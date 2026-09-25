---
name: non-production-environments-running-24-7
description: Development, staging, and QA environments run around the clock at full production-like capacity even though they're only actually used during working hours.
triggers: ["dev environment running overnight unused", "staging cost same as production", "non-prod environments never shut down", "test environment 24/7 cost waste"]
permissions: ["READ"]
---

## Symptom

A cost review reveals that non-production environments (development,
staging, QA, demo) collectively cost nearly as much as production,
despite being used only during a small fraction of the day (working
hours, active testing windows) -- they run continuously at the same
scale as if they had production-level traffic and availability
requirements.

## Likely causes

- **Non-production environments were provisioned once and left running
  indefinitely**, with no automated schedule to shut them down outside
  active usage hours, since nobody explicitly built that into the initial
  setup.
- **Non-production environments are sized similarly to production** "to
  match production as closely as possible" for testing fidelity, without
  distinguishing between configuration/behavior fidelity (which matters)
  and capacity/uptime fidelity (which usually doesn't need to match for
  a non-prod environment with far lower actual usage).
- **Shutting down and restarting environments is manual and inconvenient**
  (no tooling to automate it, state that doesn't survive a shutdown
  cleanly), so nobody bothers even though the cost benefit would be
  significant, because the operational friction of doing it manually
  outweighs the perceived benefit for any individual person.
- **Environments accumulate over time** (a new environment per major
  feature branch, per team, per demo) without a corresponding
  decommissioning process for ones no longer actively needed.

## Diagnose

1. Compare non-production environments' actual usage patterns (via
   access logs, CI/CD trigger frequency, actual working-hours activity)
   against their current always-on running schedule.
2. Calculate the cost delta between running non-production environments
   24/7 versus only during actual usage windows (e.g. 10-12 hours on
   weekdays), to quantify the specific savings opportunity.
3. Inventory all existing non-production environments and check how many
   are still actively used versus stale/abandoned (similar to the
   orphaned-resources skill in this pack, but specifically for
   environment-level, not individual-resource-level, sprawl).
4. Check what would actually break if a given non-production environment
   were stopped outside working hours -- some may have legitimate reasons
   for continuous uptime (an integration test suite that runs overnight,
   a demo environment accessed by clients in different timezones) that
   need to be identified before applying a blanket schedule.

## Fix

Implement automated start/stop scheduling for non-production
environments that don't have a legitimate need for continuous uptime,
sized to actual usage patterns (e.g. running only during working hours
on weekdays), using the cloud provider's native scheduling tools or a
simple automation script. For environments with genuine off-hours needs
(overnight test runs, cross-timezone demos), keep those specifically
running but treat the default as scheduled-down, requiring an explicit
justification to stay always-on rather than the reverse. Periodically
decommission environments no longer actively used, following the same
process as general orphaned-resource cleanup.

## Pitfalls

Don't apply an aggressive shutdown schedule without first confirming
what legitimately needs off-hours availability -- breaking an overnight
CI run or an important demo because of an overly broad shutdown policy
erodes trust in the cost-optimization effort and can lead to it being
reverted entirely. Roll out scheduling incrementally, checking with each
environment's actual users first.

## Verify

After implementing scheduling, confirm the affected environments
actually stop and start as scheduled (not just that the schedule is
configured) and confirm no legitimate workflow was broken by checking
with actual users of each environment after the first few cycles.
Measure the resulting cost reduction on the following billing cycle.
