---
name: monorepo-dependency-version-mismatch
description: Diagnose bugs caused by multiple versions of the same dependency being installed across a monorepo's workspaces (npm/yarn/pnpm), including "works in one package, broken in another" and singleton-instance bugs.
triggers: ["multiple versions of package installed", "works in one package not another monorepo", "duplicate dependency workspace", "singleton instance bug react", "peer dependency mismatch monorepo"]
permissions: ["READ"]
---

## Symptom
The same dependency behaves differently (or outright breaks) depending on
which package in the monorepo uses it, or a library that requires a
single shared instance (React, a state-management library, a database
driver's connection pool) misbehaves in ways that only make sense if two
separate copies of it are loaded simultaneously (e.g. "Invalid hook call,"
context not found across package boundaries that should share one).

## Likely causes
1. **Different packages in the monorepo depend on different major/minor
   versions of the same library**, and the package manager's hoisting
   resolves them to multiple physical copies in `node_modules` instead of
   one shared copy, because the version ranges don't overlap enough to
   dedupe.
2. **A "singleton" library (React, a DI container, some state-management
   libraries) ends up with two installed copies**, so code in package A
   and package B are technically each using "a" copy of the library, but
   not the *same* instance -- breaking anything that relies on shared
   module-level state or identity (context, hook dispatch, `instanceof`
   checks).
3. **Peer dependency versions not aligned** across workspace packages,
   so the package manager can't safely dedupe even when the ranges look
   compatible on paper, due to how peer dependency resolution rules work
   for the specific package manager in use.
4. **A workspace package pinned to an old version for a specific,
   forgotten reason**, blocking the whole monorepo's dedup for that
   dependency even after the original reason no longer applies.

## Diagnose
- Use the package manager's built-in duplicate-detection
  (`npm ls <package>`, `yarn why <package>`, `pnpm why <package>`, or a
  dedicated tool) to list every resolved version and location of the
  suspect dependency across the workspace.
- For singleton-instance bugs specifically, add a one-off debug log
  inside the library (or use the browser/Node's own module resolution
  introspection) to confirm whether two genuinely separate module
  instances are loaded, not just two dependency-tree entries that resolve
  to the same file.
- Check each workspace package's own `package.json` for the specific
  version range declared for the suspect dependency, to find which
  package's constraint is preventing a single shared resolution.

## Fix
- Align version ranges across workspace packages for dependencies that
  need to be singletons or are commonly duplicated (React, common utility
  libraries) so the package manager can resolve to one shared copy --
  many monorepo setups use a syncing tool (`syncpack` or equivalent) to
  keep versions consistent across `package.json` files automatically.
- For libraries that must be a true singleton, declare them as `peerDependencies`
  in the packages that use them (rather than direct `dependencies`),
  making the top-level application responsible for providing exactly one
  shared instance, and use the package manager's workspace protocol
  (`workspace:*`) for internal packages to ensure they resolve to the
  local, single source rather than a published version.
- Use the package manager's deduplication command
  (`npm dedupe`, `yarn dedupe`, `pnpm dedupe`) after aligning versions to
  clean up already-duplicated installs.
- Remove an outdated pinned version once the original reason for pinning
  it no longer applies, re-testing the previously-blocked package
  specifically for regressions from the version bump.

## Pitfalls
- Forcing a single version via resolution overrides
  (`resolutions`/`overrides` fields) without actually testing every
  package against the forced version can silently break a package that
  genuinely needed different behavior from an older/newer version --
  treat an override as a real upgrade for every affected package, not a
  free fix.
- Peer dependency warnings are easy to ignore in CI/local development if
  they don't fail the build, letting genuine mismatches accumulate
  silently until they cause a hard-to-trace runtime bug -- consider
  failing CI on peer dependency warnings for known-singleton libraries.

## Verify
Re-run the duplicate-detection command and confirm the previously-
duplicated dependency now resolves to exactly one version/instance across
the workspace, and confirm the specific singleton-related bug (broken
context, invalid hook call, etc.) no longer reproduces.
