---
name: dbt-selector-rebuilds-far-more-models-than-intended
description: A dbt run rebuilds far more models than expected on every invocation because of an overly broad plus-operator selector or an unintentional circular reference.
triggers: ["dbt run rebuilds entire project", "dbt selector too broad", "dbt build takes way longer than expected", "dbt plus operator rebuilding everything", "dbt circular dependency ref error"]
permissions: ["READ"]
---

## Symptom
A `dbt run` or `dbt build` invoked for what was meant to be a small,
targeted change ends up rebuilding a large fraction of the entire DAG --
run time balloons from minutes to hours, warehouse compute cost spikes,
and it's not obvious from the command alone why so many unrelated models
got touched. In a more acute version, `dbt` reports a compilation error
about a dependency cycle that didn't exist before a recent model change.

## Likely causes
1. **A `+` selector is applied at too high a level of the DAG.**
   `dbt run --select my_model+` rebuilds *everything downstream* of
   `my_model`, which is correct when `my_model`'s output genuinely
   changed, but if `my_model` sits near the root of a wide fan-out (a
   core staging model many marts depend on), `+` silently means "rebuild
   half the warehouse" even for an unrelated column addition.
2. **A model was given a broader `ref()` set than it actually needs,**
   pulling in a heavyweight upstream model just to reference one column,
   which both slows that model down directly and means any selector that
   includes its true dependencies now also touches that heavyweight
   upstream.
3. **An unintentional circular reference** was introduced -- model A
   `ref()`s model B, and B (directly, or transitively through C) `ref()`s
   A back -- often introduced when a shared "helper" model is refactored
   and ends up depending on something it also feeds, or when a business
   logic model is split into two files that end up mutually referencing
   each other.
4. **A `dbt_project.yml` or CI job config applies a scheduled full
   `dbt build` (no selector at all) when only an incremental subset
   actually needed to run,** which isn't a selector bug per se but
   produces the identical symptom of "way more rebuilds than the change
   warrants."

## Diagnose
- Run `dbt ls --select <the selector actually used> ` (list mode, no
  execution) to see the exact resolved set of models before committing to
  a real run -- this immediately shows whether `+` pulled in far more
  than intended.
- Generate and inspect the DAG visually with `dbt docs generate && dbt
  docs serve`, or read `target/manifest.json`'s `depends_on` structure
  for the specific model in question, to see its actual fan-out/fan-in
  rather than guessing from the model's apparent purpose.
- For a reported cycle, read the exact error message -- dbt reports the
  cycle's participating models directly -- and check each `ref()` call in
  those models for a dependency that shouldn't exist (often a debugging
  or convenience `ref()` added temporarily and never removed).
- Check CI/orchestration config (the Airflow task or CI job invoking
  `dbt build`) for the actual `--select`/`--exclude` flags used in
  practice versus what's documented -- a scheduled job silently running
  with no selector at all reproduces this symptom without any DAG-graph
  bug.

## Fix
Scope selectors to the smallest set that's actually correct for the
change being deployed: prefer `--select state:modified+` (build only
models that changed versus a stored manifest, plus their downstream
dependents) in CI over a blanket `+` from a hand-picked model, since it
scales with the actual diff rather than a guess about blast radius. When
a wide-fanout model genuinely needs a full downstream rebuild, treat that
as a deliberate, reviewed decision (and possibly a scheduled off-peak
job) rather than a default flag pattern used everywhere. Fix an
unintentional `ref()` by tracing why the dependency exists -- usually a
model reaches "up" for a value it should instead receive via a narrower
intermediate model, and the fix is to introduce (or point to) that
narrower model rather than looping back to the wide one. Break a genuine
circular reference by identifying which of the two models is
conceptually upstream and refactoring the other to depend on a shared
earlier-stage model instead of on its sibling.

## Pitfalls
- Switching to `state:modified+` without ensuring the comparison manifest
  (`--state` path) is actually the previous production run's manifest --
  comparing against a stale or wrong manifest silently either over- or
  under-selects, defeating the point.
- Excluding models with `--exclude` to control cost without documenting
  *why*, so a future person re-adds a broad `+` selector "to be safe"
  and reintroduces the original problem.
- Resolving a circular reference by wrapping one side in an
  `{{ ref() }}` guarded by a conditional/hack instead of restructuring
  the actual dependency -- this "compiles" but leaves the real design
  problem (two models that shouldn't need each other's output) in place.

## Verify
Run `dbt ls --select <selector>` before and after the fix and confirm the
resolved model count matches the expected, reviewed set (not just "fewer
than before" -- an exact, justified list). For a resolved circular
reference, confirm `dbt compile` (or `dbt parse`) succeeds without a
dependency-cycle error and that `dbt docs generate`'s DAG shows the
expected acyclic shape between the previously-cyclic models.
