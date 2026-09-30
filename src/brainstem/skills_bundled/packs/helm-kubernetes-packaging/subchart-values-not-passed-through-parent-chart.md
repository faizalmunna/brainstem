---
name: subchart-values-not-passed-through-parent-chart
description: A value set in the parent chart's values.yaml for a dependency subchart is ignored, and the subchart keeps using its own internal default instead.
triggers: ["subchart values not applying", "helm dependency ignoring parent values", "chart alias values not working", "helm subchart using default instead of override", "global values not reaching subchart"]
permissions: ["READ"]
---

## Symptom
The parent chart's `values.yaml` has a block that looks like it should
configure a dependency (e.g. a bundled `postgresql` or `redis` subchart,
or an internal shared subchart), but `helm template`/`helm install`
shows the subchart's resources rendered with its own built-in defaults
instead of the parent's override -- as if the parent's values block for
that dependency were never read at all.

## Likely causes
1. **Values nested under the wrong key relative to the dependency's name
   or alias** -- Helm scopes subchart values under a top-level key
   matching the dependency's `name` in `Chart.yaml`'s `dependencies`
   list, or its `alias` if one is set. A parent values.yaml with a
   `database:` block will never reach a dependency declared as `name:
   postgresql` unless an `alias: database` was also set in
   `Chart.yaml` -- otherwise Helm looks for a `postgresql:` key, finds
   nothing there, and the subchart falls back to its own defaults.
2. **Using `global` values incorrectly for what should be a
   dependency-scoped override**, or vice versa -- values under `global:`
   are passed down to every subchart and are meant for cross-cutting
   settings (e.g. `global.imageRegistry`), while a value meant only for
   one specific dependency belongs under that dependency's own key;
   putting a dependency-specific setting under `global` either doesn't
   reach the subchart's template (if the subchart's templates don't
   reference `.Values.global.x`) or leaks to unrelated subcharts that
   happen to read the same global key.
3. **Multiple aliased instances of the same chart dependency without
   distinct values blocks**, where `Chart.yaml` declares the same chart
   twice under two different aliases (e.g. a `redis` chart used as both
   `cache` and `sessions`), but the parent values.yaml only has one of
   the two alias blocks populated, or both point at the same nested
   structure by copy-paste error.
4. **Subchart's own `values.yaml` doesn't expose the field as a
   top-level override-able key at all** -- some subcharts hardcode
   values deep in their templates without surfacing them via
   `.Values.x`, so no amount of correct parent-values nesting can reach
   them; this requires either a subchart version bump that adds the
   knob, or a values override via that subchart's own supported
   mechanism (some expose an `extraEnv`/`extraArgs` escape hatch for
   exactly this gap).

## Diagnose
- Run `helm show chart <parent-chart>` and check the exact `name` and
  `alias` (if any) under `dependencies:` in `Chart.yaml` -- this is the
  authoritative key the parent values.yaml must nest under, not the
  chart's directory name or any other label.
- Run `helm template <parent-chart> --debug` and search the output for
  the subchart's rendered resources; compare the actual values baked
  into them against `helm show values <parent-chart>` scoped to that
  dependency's key, to confirm whether the parent value reached the
  render at all.
- Run `helm dependency list <parent-chart>` to confirm the subchart is
  actually a resolved, present dependency (not an unfetched/stale one --
  see the dependency-lock-version-mismatch-pulls-incompatible-subchart
  skill for that failure mode specifically).
- Check the subchart's own `values.yaml` (in `charts/<subchart>/`) for
  the exact key path the field the team is trying to override actually
  lives at -- confirm the parent's override uses the identical nested
  path, since a single misnamed intermediate key silently drops the
  entire override (Helm doesn't warn about values keys that don't match
  anything).

## Fix
Nest overrides under the exact dependency key Helm expects, matching
`alias` when one is declared:

```yaml
# Chart.yaml
dependencies:
  - name: redis
    alias: cache
    version: "18.x.x"
    repository: "https://charts.bitnami.com/bitnami"
```

```yaml
# parent values.yaml -- must use "cache", not "redis", because of the alias
cache:
  auth:
    enabled: true
  master:
    persistence:
      size: 10Gi
```

Reserve `global:` strictly for values every subchart (and the parent)
should genuinely share (registry, image pull secrets, environment
label), and confirm each subchart's documentation/values.yaml actually
reads `.Values.global.x` before relying on it. For a value the subchart
doesn't expose at all, check the subchart's changelog for a newer
version that adds the knob before resorting to a fork or a post-render
patch.

## Pitfalls
- Duplicating a value under both `global` and the dependency-specific key
  "just to be safe" produces two sources of truth that can drift, and
  makes it unclear which one a given subchart template actually reads --
  pick one, based on what the subchart's own templates reference.
- Bumping a subchart dependency version to gain a newly-exposed values
  knob without reviewing that subchart's changelog for renamed/removed
  keys elsewhere can silently break an existing override that used to
  work under the old key name.

## Verify
Run `helm template <parent-chart> | grep -A20 '# Source:
<parent-chart>/charts/<subchart>/templates/<relevant-file>.yaml'` and
confirm the specific overridden value appears in the rendered output
exactly as set in the parent's values.yaml, not the subchart's own
default.
