---
name: monorepo-shared-config-drift
description: Diagnose why lint/type-check/formatting rules pass in one monorepo package but fail in another, caused by drifted or incorrectly-extended shared configs.
triggers: ["lint passes in one package fails another", "tsconfig inconsistent monorepo", "eslint config drift", "different rules different packages monorepo", "shared config not applied"]
permissions: ["READ"]
---

## Symptom
The same class of code (a similar component, a similar function) passes
lint/type-checking in one package but fails in another within the same
monorepo, or a rule that's supposed to be enforced everywhere (via a
shared config) is silently not applied in some packages.

## Likely causes
1. **A package's local config overrides the shared base config instead of
   extending it**, replacing the intended shared rules with a narrower or
   different set, often introduced accidentally when a package's config
   was first scaffolded by copying from an unrelated example rather than
   extending the monorepo's shared config.
2. **The shared config was updated, but not every package's lockfile/
   installed version reflects the update** -- if the shared config is
   itself a versioned internal package, packages pinned to an older
   version won't see the new rules until they update their dependency
   (see `monorepo-internal-package-versioning`).
3. **A package-specific override was added for a legitimate one-off
   reason and never revisited**, so it silently continues suppressing a
   rule (or applying a different `tsconfig` target/strictness) long after
   the original reason stopped applying.
4. **Tooling resolves config differently depending on where it's invoked
   from** -- running a linter/type-checker from the repo root versus from
   within a specific package's directory can pick up different config
   files if the extends/resolution paths aren't set up consistently.

## Diagnose
- Compare the effective, fully-resolved config for the working package
  against the failing one -- most linters/type-checkers have a way to
  print the fully-resolved config (`eslint --print-config`,
  `tsc --showConfig`), which reveals overrides directly instead of
  requiring manual diffing of `extends` chains.
- Check whether the shared config is consumed as a versioned internal
  package (and if so, whether all packages are on the current version)
  or as a directly-referenced file (and if so, whether every package's
  reference path/extends statement is correct).
- Check version control history for the specific package's config file
  for an override that was added for a specific, possibly-stale reason
  (a commit message or PR often explains why).

## Fix
- Fix any local config that replaces rather than extends the shared base,
  changing it to `extends` the shared config and only override the
  specific rules that genuinely need to differ for that package, with a
  comment explaining why.
- Bump packages pinned to an outdated version of a shared internal config
  package, treating the update like any other internal dependency change
  (see `monorepo-internal-package-versioning` for the process).
- Revisit stale package-specific overrides: confirm whether the original
  reason still applies, and remove the override if it doesn't, restoring
  the shared default.
- Standardize how tooling is invoked (always from the repo root with an
  explicit per-package target, or ensure config resolution is consistent
  regardless of invocation directory) so config resolution doesn't
  silently differ based on how a script is run.

## Pitfalls
- Removing a package-specific override without understanding why it was
  added can reintroduce whatever problem it was working around -- check
  history/context before removing, and if the original reason is unclear,
  investigate rather than assuming it's safe to delete.
- Forcing every package onto identical config with no override mechanism
  at all can be too rigid for genuinely different package types (a
  Node backend package vs. a browser-targeted frontend package have some
  legitimately different lint/tsconfig needs) -- the goal is
  intentional, documented divergence, not zero divergence.

## Verify
Run the linter/type-checker with the fully-resolved-config output on both
the previously-passing and previously-failing package and confirm they
now share the same relevant rule set (except for documented, intentional
differences), and confirm the originally-failing code now produces a
consistent result across packages.
