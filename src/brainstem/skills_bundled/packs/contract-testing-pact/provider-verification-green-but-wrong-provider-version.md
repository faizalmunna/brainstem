---
name: provider-verification-green-but-wrong-provider-version
description: Provider verification passes in CI yet the actually deployed provider breaks the consumer, because verification ran against a contract or provider commit that isn't what shipped.
triggers: ["pact verification green but production broke consumer", "provider verification passed but deploy still broke integration", "pact broker can-i-deploy said yes but it failed anyway", "contract test passed in CI but real provider doesn't match"]
permissions: ["READ"]
---

## Symptom

The Pact provider verification job is green in CI, and possibly `can-i-
deploy` even approved the release, but once the provider is actually
deployed, the consumer breaks against it in staging or production --
a field is missing, a status code differs, or an endpoint 404s. Re-
reading the CI logs afterward shows verification really did pass; the
contract it verified against and the code that verified it just weren't
the pair that ended up deployed together.

## Likely causes

- **Verification ran against the consumer's latest pact from the main
  branch, not the specific pact version the deployed consumer is running**
  -- if the consumer publishes a new, incompatible contract after the
  provider's last verification but before its own deploy, the provider
  was never actually checked against what's live.
- **The provider verified against its own working-copy code, then a
  different commit got deployed** -- e.g. verification ran on a PR branch,
  but the merge commit that's actually deployed picked up an unrelated
  change that altered the response shape, and nothing re-verified after
  merge.
- **`can-i-deploy` was run with the wrong version/tag pair** (e.g.
  checking against `prod` when the target environment is `staging`, or
  checking the consumer's git SHA against a provider tag that hasn't been
  updated in the broker yet), so the compatibility check silently
  compared the wrong two versions and trivially passed.
- **The pact broker's provider version wasn't tagged/recorded at the
  moment of actual deployment** (no deploy-time `record-deployment` or
  equivalent call), so later `can-i-deploy` checks reason about a provider
  version that was never actually running in that environment.

## Diagnose

1. In the Pact Broker UI (or `pact-broker matrix`), pull up the exact
   consumer version and provider version pair that was live at the time
   of the incident, and check whether a verification result actually
   exists for that specific pair -- not just "some verification passed
   recently."
2. Compare the git SHA recorded against the provider verification result
   to the git SHA that was actually deployed (check your deploy tool's
   release log or the `/version` endpoint if the provider exposes one) --
   a mismatch here is the smoking gun.
3. Check whether `can-i-deploy` was invoked with `--to-environment` (or
   equivalent) matching the real target, and confirm the tags/branches
   passed match your deployment pipeline's actual promotion flow.
4. Look for a gap in automation: is there a CI step that publishes the
   provider's verification result back to the broker on every merge to
   the deploy branch, and a deploy-time hook that records which version
   is now live in each environment? Missing either one breaks the chain
   this system depends on.

## Fix

Treat the Pact Broker's version/environment records as the source of
truth for "what's actually running where," not just a side effect of
running tests. Wire `pact-broker record-deployment` (or your framework's
equivalent) into the actual deploy step for both consumer and provider,
so the broker always reflects reality, and make `can-i-deploy` a hard
gate in the pipeline immediately before that deploy step (not earlier,
and not as an informational-only check) using the exact version and
target environment being deployed. Ensure provider verification is
re-triggered by a webhook whenever a new consumer contract is published,
so verification results stay fresh against the provider's current main
branch rather than going stale between consumer releases.

## Pitfalls

Don't treat "provider verification passed once, at some point" as
permanent proof of compatibility -- contracts and providers both drift
over time, and a stale green checkmark is more dangerous than no check at
all because it creates false confidence. Also don't run `can-i-deploy`
against a branch tag (like `main`) when multiple environments deploy from
that branch at different times -- use environment-specific deployment
records so the matrix reflects what's live in staging versus production
independently.

## Verify

Deliberately publish a new consumer contract with an incompatible change,
without deploying the provider fix, and confirm `can-i-deploy` for the
consumer's release now returns a hard failure referencing the correct
provider version. Then run the full deploy pipeline end to end and check
the Pact Broker matrix afterward to confirm both the consumer and
provider's new versions were recorded as deployed to the correct
environment automatically, not just verified in isolation.
