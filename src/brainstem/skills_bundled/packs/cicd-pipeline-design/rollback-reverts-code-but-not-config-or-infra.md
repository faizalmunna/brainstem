---
name: rollback-reverts-code-but-not-config-or-infra
description: Rolling back to a previous application version still fails because associated configuration, infrastructure, or feature-flag defaults were not reverted alongside it.
triggers: ["rollback still broken after reverting code", "config out of sync after rollback", "infra changes not rolled back with app", "rollback incomplete environment variable", "reverted app version but env still wrong"]
permissions: ["READ"]
---

## Symptom
A bad release is rolled back by redeploying the previous application
artifact, but the system still misbehaves afterward -- because
environment variables, feature-flag defaults, infrastructure resources
(a queue, a new required IAM permission, an updated load balancer rule),
or third-party service configuration that were changed *alongside* the
bad release were never reverted, leaving the old application code running
against a new, incompatible environment. This is the same family of
problem as an app/database schema mismatch, but shows up in config and
infrastructure rather than the database specifically.

## Likely causes
1. **Configuration changes are deployed out-of-band from the application
   artifact** -- environment variables, secrets, or feature-flag defaults
   are updated through a separate manual step, a different pipeline, or a
   different team's process, so "roll back the app" and "roll back its
   configuration" are two different, unlinked actions and only the first
   one is part of the documented rollback procedure.
2. **Infrastructure changes accompanying the release are provisioned
   through a separate, forward-only process** (a manually-applied
   Terraform change, a console click to add a new queue or permission)
   that isn't versioned or tied to the application release, so there's no
   "previous state" to revert to even if someone thought to.
3. **The new release assumed the presence of something the rollback
   doesn't remove** -- e.g. the new version writes messages in a new
   format to a shared queue, and old consumers (now running again after
   rollback) can't parse messages already produced in the new format that
   are still in flight.
4. **Rollback runbooks/automation were written once, early, and never
   updated as the deploy process grew more moving parts** -- the runbook
   still only describes "redeploy the previous image tag" from when that
   was sufficient, and nobody revisited it as config and infra became
   part of typical releases.

## Diagnose
- List every change that shipped alongside the bad release, not just the
  code diff -- check for accompanying config/env var changes, feature
  flag changes, and infrastructure changes (search the infra-as-code
  history and any manual change log for the same time window).
- For each accompanying change, determine whether the previous
  application version can function correctly with it left in its new
  state, or whether it specifically requires the old state -- this
  distinguishes changes that are safe to leave forward from ones that
  actively need reverting.
- Check whether config/infra changes for this release are versioned and
  tied to the same release identifier as the app artifact, or applied
  through an entirely separate, untracked process.
- Review the actual rollback runbook/automation used and compare its
  scope (what it touches) against the full list of things that changed --
  identify the gap directly.

## Fix
Bundle configuration and infrastructure changes into the same
versioned, reviewable unit as the application code they support (config
as code, infrastructure as code, feature flags with recorded state
history) so that a rollback of "this release" has a well-defined,
complete scope rather than being implicitly limited to whatever the
deploy tool's own default rollback command happens to touch. Where a
release requires a coordinated config or infra change, design it the
same way as a database migration: make the change backward-compatible
first (the old version must tolerate the new config/infra state) before
or independently of the code that depends on it, so rollback doesn't
require perfectly reverse-engineering every accompanying change under
incident pressure.

## Pitfalls
- Writing a rollback automation that reverts everything indiscriminately,
  including infra/config changes that are safe and even necessary to
  leave in the new state (e.g. a monitoring improvement, an unrelated
  security patch that shipped in the same window) can itself cause a
  regression -- rollback scope should be deliberate, not "revert
  everything that changed recently."
- Treating this purely as a tooling gap without also updating the
  runbook/mental model of what "rollback" means for the team -- even
  well-designed tooling doesn't help if responders under incident
  pressure still only think to revert the application artifact.

## Verify
For the next release that includes a config or infrastructure change,
deliberately perform a full rollback in a staging environment (not just
the app artifact) and confirm the previous application version runs
correctly against the resulting state, with no manual out-of-band steps
required beyond what the documented/automated rollback procedure
performed.
