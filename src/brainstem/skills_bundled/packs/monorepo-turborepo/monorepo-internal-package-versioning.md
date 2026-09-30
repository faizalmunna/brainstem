---
name: monorepo-internal-package-versioning
description: Decide how to version and publish internal/shared packages in a monorepo (changesets vs. always-latest workspace versions) and diagnose consumers breaking from an internal package change.
triggers: ["how to version monorepo packages", "changesets", "internal package breaking change", "shared package versioning strategy", "publish workspace package"]
permissions: ["READ"]
---

## Symptom
Either a design question (how should internal packages be versioned --
independently published with semver, or just always consumed at their
current workspace version), or a concrete incident: a change to a shared
internal package broke one or more consumers because there was no process
catching the incompatibility before it merged.

## Likely causes
1. **No changelog/versioning discipline for internal packages** -- changes
   ship directly to the workspace version consumers use, with no
   explicit signal (a version bump, a changelog entry) that a breaking
   change occurred, relying entirely on manual coordination or luck.
2. **A shared package published externally (to a registry, for other
   teams/repos to consume) without a clear semver policy**, so consumers
   outside the monorepo can't tell a patch from a breaking change from
   the version number alone.
3. **No CI check that runs affected consumers' tests against a shared
   package's change before merge**, so a breaking change to a widely-used
   internal package is only discovered after landing on `main`, or after
   deploy.
4. **Ambiguity about who owns coordinating a breaking change** across
   multiple consumer teams, so it either doesn't happen at all or happens
   unilaterally without warning.

## Diagnose
- Check whether internal packages have any versioning scheme at all
  (workspace-only "always current" vs. independently semver-versioned
  with a changelog).
- For a specific breakage, check whether the change to the shared package
  was reviewed with visibility into which consumers depend on the
  changed API (a monorepo-wide "who imports this" check), or reviewed in
  isolation without that context.
- Check CI configuration for whether a change to a shared package
  triggers tests in its consumers (see `nx-affected-not-detecting-changes`/
  `turborepo-task-graph-ordering` for the mechanics of that detection).

## Fix
- For packages only ever consumed *within* the monorepo (never published
  externally), workspace-version consumption (always using the current
  source via the workspace protocol) is usually simpler and sufficient --
  but pair it with CI that runs affected consumers' tests on every change
  to the shared package, so breakage is caught before merge, not after.
- For packages published externally (to npm, to other teams/repos), adopt
  an explicit changeset-based workflow (e.g. the `changesets` tool):
  contributors declare the semver impact (patch/minor/major) and a
  changelog entry as part of the PR introducing the change, and a release
  process consumes those declarations to version and publish
  consistently.
- Use the affected-consumer test run as the actual gate for whether a
  shared-package change is safe to merge -- a change that doesn't break
  any consumer's tests is a strong (though not absolute) signal it's
  backward-compatible; one that does needs an explicit, coordinated
  update to those consumers as part of the same change, not a follow-up
  "someone else's problem."
- For breaking changes affecting multiple consumer teams, communicate
  and coordinate explicitly (a deprecation period, a migration guide)
  rather than merging silently and letting each team discover it
  independently.

## Pitfalls
- Adopting a full independent-semver-with-changelog process for packages
  that are only ever consumed within the same monorepo, by the same team,
  adds process overhead without a corresponding benefit -- match the
  process weight to whether the package actually crosses a real
  organizational or publishing boundary.
- Relying solely on "CI didn't break" as sufficient signal for a
  behavioral (not just type-level) breaking change misses cases where
  tests don't cover the affected behavior -- pair automated checks with
  actual review attention to the specific API surface being changed.

## Verify
For a changeset-based release, confirm the generated changelog and
version bump accurately reflect the actual change's impact (a behavioral
breaking change should never ship as a patch version); for a workspace-
consumed internal change, confirm CI actually ran and passed every real
consumer's test suite before merge, not just the changed package's own
tests.
