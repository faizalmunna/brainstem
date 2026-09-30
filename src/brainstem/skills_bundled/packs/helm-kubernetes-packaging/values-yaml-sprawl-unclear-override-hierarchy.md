---
name: values-yaml-sprawl-unclear-override-hierarchy
description: A chart's values.yaml and per-environment override files have grown to hundreds of lines each, making it unclear which value actually applies for a given deployment.
triggers: ["which values file wins in helm", "values.yaml too big to reason about", "not sure what value is actually applied helm", "helm values override order confusing", "too many environment values files"]
permissions: ["READ"]
---

## Symptom
The chart has a base `values.yaml` plus `values-dev.yaml`,
`values-staging.yaml`, `values-prod.yaml` (sometimes per-region or
per-tenant variants on top of those), each hundreds of lines long with
heavy duplication. Nobody on the team can answer "what is the actual
value of `resources.limits.memory` in prod" without running a command --
and when someone changes the base `values.yaml` to fix one environment,
it silently changes behavior in others that weren't touched.

## Likely causes
1. **Full copy-paste of values.yaml per environment** rather than a thin
   override file containing only the deltas -- every environment file
   has all 300 keys, so a key present but different in only one
   environment is indistinguishable, at a glance, from 299 keys that are
   just accidentally duplicated and now drifting independently.
2. **No documented or enforced merge order** -- the team doesn't have a
   single source of truth for the `-f` flag order used in CI/deploy
   scripts (`-f values.yaml -f values-prod.yaml -f values-prod-us.yaml`),
   so different engineers invoke `helm upgrade` with different flag
   orders locally vs. in the pipeline, producing different effective
   values from the "same" files.
3. **Deeply nested values structures with no flattening discipline**,
   where a single logical override (e.g. "prod uses more replicas")
   requires repeating an entire nested map because YAML map merging in
   Helm is a full replace at the first differing key, not a deep merge
   at the leaf -- see the values-map-merge-replaces-entire-block skill
   for the mechanics; the sprawl symptom here is the accumulated result
   of repeatedly working around that by duplicating whole blocks.
4. **No values schema (`values.schema.json`)**, so nothing catches a typo
   introducing a new, unused key that looks like an override but is
   actually silently ignored because it doesn't match any `{{ .Values.x
   }}` path in the templates.

## Diagnose
- Run `helm template . -f values.yaml -f values-<env>.yaml` for each
  environment and diff the rendered output between environments --
  anywhere the rendered manifests are identical despite the values files
  differing indicates dead/unused override keys; anywhere they differ
  unexpectedly indicates a base value leaking through inconsistently.
- Run `helm show values <chart> -f values-<env>.yaml` (or `helm get
  values <release> -a` on a live release) to see Helm's own computed
  effective values, rather than eyeballing multiple files and mentally
  merging them.
- Grep each environment values file for keys that also exist, with the
  identical value, in the base `values.yaml` -- these are pure
  duplication contributing to sprawl with zero behavioral purpose.
- Check whether the deploy pipeline's `-f` flag order matches what's
  documented (if anything is documented at all); a mismatch here means
  "what's in the files" and "what's actually deployed" have already
  diverged.

## Fix
Restructure environment files to contain only deltas from the base, and
make the override hierarchy explicit and singular:
- Keep `values.yaml` as the common/default baseline with sane
  lowest-common-denominator settings.
- Reduce each `values-<env>.yaml` to only the keys that actually differ
  for that environment -- if a value is the same as the base, delete it
  from the override file; the base already provides it.
- Adopt one canonical, scripted invocation order (a `Makefile` target or
  CI job step, not a comment in a README) so there is exactly one place
  that defines "prod = base + values-prod.yaml + values-prod-secrets.yaml"
  and every human and pipeline path calls that, rather than typing `-f`
  flags by hand.
- Add a `values.schema.json` with the allowed keys and types so an
  override introducing an unrecognized key fails `helm lint`/`helm
  install --dry-run` instead of being silently ignored.
- For genuinely deep, orthogonal variation (e.g. per-tenant AND
  per-region), consider splitting into a values-generation step
  (templated values via a small script, or a values file per axis merged
  by the deploy tool) rather than a hand-maintained matrix of files.

## Pitfalls
- Aggressively "cleaning up" an environment values file by deleting keys
  that look redundant without first diffing rendered output can silently
  revert a deliberate, undocumented override someone added for a reason
  (e.g. a prod-only resource limit bump made during an incident) --
  always diff `helm template` output before and after trimming.
- Introducing a values schema retroactively on a chart with years of
  accumulated environment files often immediately fails validation on
  existing typo'd keys that were silently ignored for a long time --
  budget time to triage each schema violation rather than treating this
  as a quick drop-in.

## Verify
For each environment, run `helm template . -f values.yaml -f
values-<env>.yaml` before and after the values restructuring and confirm
the rendered manifest output is byte-identical (a deliberate diff should
be the ONLY exception, and should be called out explicitly) -- this
proves the deltas-only refactor didn't change actual deployed behavior.
