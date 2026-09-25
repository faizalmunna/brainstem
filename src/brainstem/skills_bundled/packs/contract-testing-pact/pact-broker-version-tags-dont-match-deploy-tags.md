---
name: pact-broker-version-tags-dont-match-deploy-tags
description: The pact broker compatibility matrix becomes untrustworthy because version tags recorded there drift out of sync with what each environment's deployment pipeline actually uses.
triggers: ["pact broker tags out of sync with deployment", "can-i-deploy matrix untrustworthy", "pact version tagging inconsistent across environments", "pact broker environment tags don't match real deploys"]
permissions: ["READ"]
---

## Symptom

Engineers stop trusting the Pact Broker's compatibility matrix -- someone
notices `can-i-deploy` says a pairing is safe for `production` when it
clearly wasn't verified against what's actually running there, or the
matrix shows a provider version tagged `prod` that was actually rolled
back weeks ago. Once this happens once, teams start skipping the gate
"just this once," and the whole point of automated compatibility checking
erodes.

## Likely causes

- **Tags are applied manually or inconsistently by different pipelines**
  (one service's CI tags with the branch name, another tags with the
  environment name, another doesn't tag at all), so there's no single
  consistent scheme mapping a pact broker tag to "what is actually
  deployed to environment X right now."
- **Tags are set at build/publish time but never updated or removed on
  rollback** -- a version gets tagged `production` on deploy, but when
  that release is rolled back, nothing moves the `production` tag back to
  the previous version, so the broker keeps claiming a since-reverted
  version is live.
- **Old-style branch/version tags are used instead of the Pact Broker's
  environment-and-deployment-tracking features** (`record-deployment`,
  `record-release`, environments), so there's no first-class distinction
  between "this version was ever released" and "this version is
  currently deployed here," which the matrix needs to answer
  `can-i-deploy` correctly.
- **Multiple environments (staging, prod, regional deployments) share a
  single generic tag** like `deployed`, collapsing distinct environments
  into one signal, so a check meant for production incorrectly considers
  a staging-only verification as evidence of safety.

## Diagnose

1. Pick a service currently deployed to production and check, in the
   Pact Broker, which version/tag the broker currently associates with
   that environment -- then compare that against what your deployment
   tool (e.g. the CD system's release history) says is actually running.
   A mismatch here reproduces the trust problem directly.
2. Search the deploy pipeline scripts for every place a pact tag is
   applied (`pact-broker create-version-tag`, `pact publish --tag`, or
   older CLI flags) and list out the actual tag strings used across all
   services -- inconsistent naming schemes will be obvious once listed
   side by side.
3. Check whether a rollback runbook or script exists that updates pact
   broker records, or whether rollbacks only touch the deployment
   infrastructure and leave the broker stale.
4. Check the Pact Broker version to confirm whether first-class
   "environments" and `record-deployment`/`record-release` support is
   available and simply unused -- most drift comes from teams having
   started with ad hoc tags before this feature existed and never
   migrating.

## Fix

Standardize on the Pact Broker's environment and deployment-tracking
model rather than freeform tags: define explicit environments (e.g.
`staging`, `production`) once, and call `record-deployment` (for
long-running services) or `record-release` (for consumer app releases)
at actual deploy time from the deploy pipeline itself -- never as a
manual or best-effort step. Critically, call `record-undeployment` (or
re-run `record-deployment` with the rolled-back version) as part of the
rollback procedure, so a rollback is not complete until the broker
reflects it. Run `can-i-deploy --to-environment <env>` using these
records as the actual gate before every deploy, for every service in the
dependency graph.

## Pitfalls

Don't treat migrating to proper environment tracking as optional cleanup
to get to "later" -- every day spent on inconsistent freeform tags is
another day the matrix can lie to someone, and partial migration (some
services on environments, others still on ad hoc tags) actually makes
things more confusing because `can-i-deploy` behaves differently
depending on which convention a given service happens to use. Migrate a
full dependency chain (consumer and all its providers) together, not one
service at a time in isolation.

## Verify

Deploy a service to a test/staging environment through the real pipeline
and confirm the Pact Broker's environment view immediately reflects it as
currently deployed there. Then simulate a rollback through the real
rollback procedure and confirm the broker updates accordingly (the
rolled-back version is no longer shown as deployed, and/or the restored
previous version is). Finally, run `can-i-deploy` for a pairing you know
should fail (an unverified version) and confirm it correctly blocks,
using the environment-based records rather than any leftover freeform
tag.
