---
name: nx-affected-not-detecting-changes
description: Diagnose Nx's (or Turborepo's) "affected" detection missing a project that should have been flagged as impacted by a change, causing CI to skip tests/builds it shouldn't.
triggers: ["nx affected not working", "affected projects wrong", "ci skipped tests that should run", "nx affected missing project", "monorepo change detection wrong"]
permissions: ["READ"]
---

## Symptom
`nx affected` (or Turborepo's equivalent filtered execution) doesn't
include a project in its computed set even though a change was made that
should logically affect it -- meaning CI skips building/testing that
project, and a real regression can slip through undetected.

## Likely causes
1. **The dependency isn't declared where the tool's graph analysis looks
   for it** -- Nx builds its project graph primarily from explicit
   imports/`package.json` dependencies; a runtime-only relationship (a
   shared config file read at runtime, a generated file, a dynamic
   `import()` the static analyzer doesn't follow) won't be captured.
2. **The base/comparison commit used for "affected" is wrong** -- comparing
   against the wrong branch or an outdated base ref makes the tool think
   fewer (or more) files changed than actually did relative to what the
   team intends "affected" to mean for this CI run.
3. **A shared, non-code file changed** (a schema, a fixture, a
   generated-code source file) that logically should mark dependents as
   affected, but isn't wired into the tool's implicit-dependency
   configuration.
4. **The project's `project.json`/config doesn't declare a real
   `implicitDependencies` relationship** for something outside normal
   import-graph detection (e.g. "this app depends on this OpenAPI spec
   file even though it doesn't `import` it directly").

## Diagnose
- Run the affected command with verbose/graph output
  (`nx graph`/`nx affected:graph` or Turborepo's `--graph`) to visualize
  what the tool currently believes depends on what, and compare against
  the real intended relationship.
- Check the actual base/head refs the affected command is comparing
  (`nx affected --base=... --head=...`) against what CI is configured to
  pass -- a misconfigured base ref is a common, easy-to-miss cause,
  especially after a branching strategy change.
- Identify the specific relationship the tool missed: is it a real code
  import the analyzer should have caught (a possible tool bug/limitation
  worth reporting), or a non-import relationship (shared non-code file,
  runtime-only coupling) the tool was never going to infer automatically?

## Fix
- For non-import relationships the tool can't infer from code, declare
  them explicitly as `implicitDependencies` (Nx) or the Turborepo
  equivalent (`inputs` referencing the shared file across the dependent
  package's task config) so a change to that shared file correctly marks
  dependents as affected.
- Fix the base/head ref configuration in CI to match the team's actual
  intended comparison (usually the merge-base with the target branch, not
  just the previous commit) so affected detection reflects the real set
  of changes in a PR.
- For dynamic imports or other patterns the static analyzer doesn't
  follow, either restructure to a statically-analyzable import where
  practical, or add an explicit implicit dependency declaration as a
  deliberate override.
- As a safety net for critical shared code, consider a CI rule that runs
  a broader (or full) test suite on changes to specific high-blast-radius
  files (core shared libraries, build configuration) regardless of what
  affected-detection computes, rather than trusting automatic detection
  alone for the highest-risk paths.

## Pitfalls
- Declaring overly broad `implicitDependencies` (marking many projects as
  depending on a frequently-changed file) defeats the purpose of affected
  detection by making most changes mark most projects as affected anyway
  -- scope implicit dependencies precisely to genuine relationships.
- Fixing the immediate missed case without re-auditing the base/head ref
  configuration can leave the same class of bug (wrong comparison range)
  to recur for a different file/project next time.

## Verify
Make the same kind of change that was previously missed and confirm the
affected command now correctly includes the expected project, then make
an unrelated change and confirm the previously-missed project is
correctly excluded (not overcorrected into always being affected).
