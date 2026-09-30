---
name: production-only-leak-not-reproducible-in-staging
description: A confirmed memory leak occurs reliably in production but cannot be reproduced in staging or development environments despite apparently similar configuration.
triggers: ["memory leak only in production", "cannot reproduce leak in staging", "leak works fine in dev fails in prod", "production specific memory issue"]
permissions: ["READ"]
---

## Symptom

Production monitoring clearly shows a memory leak (steady growth leading
to eventual OOM/restart), but attempts to reproduce the same behavior in
staging or development environments -- even ones configured to closely
resemble production -- consistently fail to show the same growth
pattern, blocking normal debugging workflows that rely on local
reproduction.

## Likely causes

- **Production traffic volume and diversity is much higher than staging
  can realistically replicate**, and the leak requires a scale or
  diversity of input that only production's real, varied traffic
  actually produces.
- **A production-specific configuration difference** (a feature flag
  enabled only in production, a different connection pool size, a
  different cache configuration) triggers a code path that staging's
  configuration doesn't exercise at all.
- **Production runs for much longer continuous uptime than staging**
  (which might be redeployed/restarted frequently), so a very slow
  per-operation leak that would eventually show up in staging too simply
  hasn't had enough cumulative time to become visible there.
- **Production-specific integrations or dependencies** (a real external
  service staging mocks or stubs out) behave differently than their
  staging equivalents in a way that specifically triggers the leak (an
  error path, a specific response shape) that the staging mock never
  produces.

## Diagnose

1. Compare production and staging configuration in detail (feature
   flags, connection pool sizes, cache settings, environment variables)
   for any difference that could plausibly relate to the leak's
   suspected cause.
2. Compare traffic characteristics (volume, request diversity, specific
   endpoints hit, error rates) between production and staging to assess
   whether staging's traffic pattern could plausibly ever trigger the
   same code path.
3. Check how long staging environments typically run before being
   redeployed/restarted, and estimate whether that's long enough to
   reveal a slow leak based on the observed production growth rate.
4. Check whether any production dependency is mocked/stubbed differently
   in staging, and whether that mock's behavior differs meaningfully
   from the real dependency's actual behavior (especially on error
   paths).

## Fix

Once a specific configuration or traffic-pattern difference is
identified as the likely trigger, replicate that specific difference in
a staging or dedicated debugging environment (enable the same feature
flag, replay a sample of real production traffic, use the real
dependency instead of a mock for the specific interaction in question) to
achieve reproduction. If traffic volume/diversity is the limiting
factor, consider replaying anonymized production traffic logs against a
staging instance rather than relying on synthetic test traffic. If
reproduction genuinely requires production-scale conditions, use
production-safe diagnostic tooling (careful, targeted heap sampling with
minimal performance impact) directly against a canary or small
percentage of production traffic instead.

## Pitfalls

Don't give up on reproduction and resort purely to trial-and-error fixes
tested only via full production deploys -- that's slow and risky
compared to even a partial, closer-to-production reproduction
environment; invest in closing the specific gap (traffic, config, or
dependency behavior) that's preventing reproduction.

## Verify

Once reproduction is achieved in a non-production environment using the
identified trigger, apply the fix there and confirm the leak no longer
occurs under the same reproduction conditions. Deploy to production and
monitor the previously-affected metric over an extended period to
confirm the fix holds under real conditions too.
