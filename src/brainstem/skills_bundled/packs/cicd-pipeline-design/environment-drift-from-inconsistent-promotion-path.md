---
name: environment-drift-from-inconsistent-promotion-path
description: A release behaves differently in production than it did in staging because the two environments were not deployed through the same promotion path.
triggers: ["works in staging but not production", "environments have drifted apart", "different config between staging and prod pipeline", "staging passed but prod deploy different behavior", "promotion path inconsistent across environments"]
permissions: ["READ"]
---

## Symptom
A release is validated in staging (or a pre-prod environment) and passes
every check, but behaves differently once promoted to production --
not due to a legitimate environment-specific configuration difference
(scale, real credentials), but because production was actually deployed
through a meaningfully different path than staging was: a different
pipeline definition, a manually-run step that staging's automated
pipeline doesn't have, or a different artifact than the one that was
actually tested.

## Likely causes
1. **Staging and production are deployed by separate pipeline
   definitions** (not the same pipeline parameterized by environment)
   that have drifted apart over time as each was edited independently for
   environment-specific fixes, so "passed in staging" no longer implies
   anything reliable about what production's differently-configured
   pipeline will actually do.
2. **The artifact is rebuilt for production rather than promoted** -- a
   fresh build triggered separately for the production deploy (rather
   than deploying the exact same build artifact that was validated in
   staging) can differ due to a dependency version resolved differently
   between build times, a non-deterministic build step, or a source
   change that landed between the two builds.
3. **Production has manual or undocumented steps that staging's pipeline
   doesn't exercise** -- a manual configuration tweak, a one-off script
   run by an operator during past incidents that became implicit
   tribal-knowledge practice, or a production-only pre/post-deploy hook
   that was added directly to production tooling and never mirrored into
   the staging path.
4. **Environment-specific configuration values are managed inconsistently**
   -- staging and production configs are maintained as separately
   hand-edited files/secrets rather than derived from a shared template
   with explicit per-environment overrides, so they can silently diverge
   in ways nobody intended (a flag left different, a timeout value that
   was tuned in one place and forgotten in the other).

## Diagnose
- Diff the actual pipeline definitions (not just their intended
  descriptions) used to deploy staging versus production for this
  release -- look for steps present in one but not the other, or
  differently-ordered/differently-configured steps.
- Confirm whether the artifact deployed to production is the identical
  build (same digest/hash) that was validated in staging, or a separate
  build -- if separate, that's independently a traceability problem worth
  fixing regardless of this specific incident.
- Interview whoever performed the production deploy (or check the
  deploy's audit log/history) for any manual step taken that isn't
  encoded in the pipeline definition itself.
- Diff the effective configuration (resolved environment variables,
  feature flag states, resource limits) between staging and production
  at the time of the incident, not just the checked-in template files,
  since a manual override can exist only in the live environment.

## Fix
Use a single parameterized pipeline definition for all environments
(staging and production run through the same pipeline code path, differing
only in explicit, reviewed parameters/environment-scoped config), and
promote the exact validated artifact (by digest, not by rebuilding) from
staging to production rather than triggering an independent production
build. Bring any manual or undocumented production-only step into the
pipeline definition itself -- if a step is important enough to matter,
it belongs in code, not in an operator's memory -- and manage
per-environment configuration from a shared source with explicit,
reviewed overrides per environment rather than independently hand-edited
files that can silently diverge.

## Pitfalls
- Unifying the pipeline definition but leaving production-specific manual
  overrides in place "just for now" during the migration reintroduces the
  exact drift being fixed and is easy to forget about once the
  higher-visibility unification work is declared done -- track and
  eliminate every manual override explicitly, not just the pipeline
  structure.
- Assuming identical pipeline code guarantees identical behavior without
  verifying the *resolved* configuration is also equivalent apart from
  intended differences -- two environments can run the same pipeline and
  still drift purely through configuration value divergence over time.

## Verify
Trigger a deploy of the same release to both staging and production
through the now-unified pipeline and diff the full resolved configuration
and artifact digest between the two runs, confirming they're identical
except for the specific, intended environment-scoped parameters (e.g.
replica count, external endpoint URLs) -- and confirm no manual step was
required in either environment to reach a working state.
