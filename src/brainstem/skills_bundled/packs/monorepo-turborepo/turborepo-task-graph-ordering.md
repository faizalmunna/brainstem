---
name: turborepo-task-graph-ordering
description: Fix a Turborepo/Nx monorepo where a package builds against a stale version of another internal package's output because the task dependency graph is incomplete.
triggers: ["monorepo stale build", "package builds before dependency", "turbo dependson missing", "internal package not rebuilt", "monorepo build order wrong"]
permissions: ["READ"]
---

## Symptom
A package in the monorepo builds successfully but behaves as if an
internal dependency (another package in the same monorepo) hadn't
received its latest change -- the consuming package was built against a
stale compiled output of the dependency because the build system ran
tasks in the wrong order, or ran them in parallel when one genuinely
needed to finish first.

## Likely causes
1. **Missing `dependsOn: ["^build"]`** (or the Nx equivalent) on a
   package's build task, so Turborepo doesn't know it needs the
   dependency package's build to complete first and may run them in
   parallel or in an arbitrary order.
2. **The dependency is declared in `package.json` but the task graph
   config doesn't reflect it** -- Turborepo infers the workspace
   dependency graph from package manifests, but a task's own `dependsOn`
   still needs to reference the right task name (`^build` for "this
   package's dependencies' build tasks") for ordering to actually apply
   to that specific task.
3. **A package consumes another's *source* directly (e.g. via a bundler
   alias) in development but its *compiled output* in a specific build
   task**, so the two modes have different real dependency requirements
   that a single `dependsOn` configuration doesn't cleanly capture.
4. **A circular dependency between packages** that the graph can't
   linearize at all, which may surface as inconsistent behavior depending
   on execution order rather than a clean error (see the separate
   `monorepo-circular-dependency` skill for that specific case).

## Diagnose
- Run `turbo run build --graph` (or the equivalent dependency-graph
  visualization for the tool in use) to see the actual computed task
  execution order and confirm whether the dependency's build task is
  ordered before the consumer's.
- Check the consuming package's `turbo.json` task definition for
  `dependsOn` referencing `^build` (or the specific task name), and cross-
  check that the dependency is actually listed in `package.json` so the
  workspace graph even knows about the relationship.
- Reproduce concretely: make a change to the dependency package, run the
  consumer's build task alone (not the dependency's), and check whether
  the dependency was rebuilt first automatically or the consumer used a
  stale compiled artifact.

## Fix
- Add `"dependsOn": ["^build"]` (or the appropriate task reference) to
  every task that requires its workspace dependencies to be built first,
  so Turborepo's scheduler orders them correctly and won't run them in
  parallel when a real ordering dependency exists.
- Ensure the workspace dependency itself is correctly declared (a real
  `package.json` dependency, using the workspace protocol) so Turborepo's
  inferred graph includes the relationship at all -- `dependsOn: ["^build"]`
  only has something to order if the underlying package dependency is
  recognized.
- For packages consumed as source in dev but compiled output in
  production builds, make that distinction explicit in the task
  configuration (separate dev/build task pipelines) rather than relying
  on one `dependsOn` setup to correctly handle both modes.
- Resolve any genuine circular dependency (restructure to remove the
  cycle) rather than trying to force an ordering onto a graph that
  fundamentally can't be linearized.

## Pitfalls
- Adding `dependsOn: ["^build"]` broadly to every task "to be safe" can
  serialize work that didn't actually need to be sequential, reducing the
  parallelism benefit that made adopting Turborepo/Nx worthwhile in the
  first place -- apply it specifically where a real build-order
  dependency exists.
- A stale build passing silently (no error, just wrong behavior) is
  easy to miss in code review and only shows up as a confusing runtime
  bug in the consuming package -- treat any report of "this package isn't
  seeing my change" in a monorepo as a task-graph question first, not
  purely an application-logic bug.

## Verify
Make a change to the dependency package and run only the consumer's
build/test task (not the dependency's directly) and confirm the
dependency task runs automatically first, and that the consumer's
behavior reflects the new change -- not a cached, stale version of the
dependency's output.
