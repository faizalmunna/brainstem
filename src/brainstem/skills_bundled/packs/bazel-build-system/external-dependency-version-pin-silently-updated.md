---
name: external-dependency-version-pin-silently-updated
description: An external dependency fetched by Bazel resolves to a different version than the one pinned in the lock file, because the pin references a mutable ref instead of an immutable, content-addressed one.
triggers: ["bazel external dependency changed unexpectedly", "http_archive version drift", "bazel workspace dependency not actually pinned", "external repo silently updated"]
permissions: ["READ"]
---

## Symptom

A build that was working correctly suddenly behaves differently (a new
bug appears, a previously-passing test fails) with no corresponding
change to the repository's own source code, traced back to an external
dependency fetched via Bazel (`http_archive`, a Git-based external
repository rule) resolving to different actual content than before,
despite the dependency appearing to be "pinned" in configuration.

## Likely causes

- **An `http_archive` or similar rule references a URL that points at a
  mutable target** (a branch name, a "latest" tag, a GitHub archive URL
  for a branch rather than a specific commit/tag), so the actual content
  fetched can change over time even though the Bazel configuration
  itself never changed.
- **A `sha256` integrity check was omitted or was present but not
  actually enforced** in the dependency-fetching rule, removing the
  safety net that would otherwise cause a build failure (rather than
  silent content drift) if the fetched content ever didn't match what
  was expected.
- **A transitive external dependency (pulled in by a directly declared
  one) isn't pinned at all**, and its own upstream source changed,
  affecting the build even though every directly-declared dependency in
  the project's own configuration looks unchanged.
- **A dependency-management tool or lock file generation process has a
  bug or gap** that fails to actually pin every dependency it claims to
  manage, giving a false sense of full reproducibility.

## Diagnose

1. Identify the specific external dependency responsible for the
   behavior change by bisecting (temporarily pinning to a known-older
   fetch, or comparing fetched content hashes across time if available).
2. Check the dependency's declaration for whether it references an
   immutable identifier (a specific commit SHA, a tagged release archive
   with a verified `sha256`) versus a mutable one (a branch name, an
   unpinned "latest" reference).
3. Check whether a `sha256` integrity hash is present and actually being
   enforced for the dependency's fetch rule.
4. Trace the dependency graph for any transitively-pulled dependency that
   isn't itself pinned, which could be the actual source of drift even if
   direct dependencies all look correctly pinned.

## Fix

Pin every external dependency to an immutable, content-addressed
reference -- a specific commit SHA (not a branch name) for Git-based
fetches, and always include and enforce a `sha256` integrity hash for
`http_archive`-style fetches, so any content mismatch causes a loud,
immediate build failure rather than silent drift. Audit the full
transitive dependency graph (not just directly declared dependencies)
for the same pinning discipline, since an unpinned transitive dependency
undermines the reproducibility guarantee the direct dependencies were
trying to provide.

## Pitfalls

Don't add a `sha256` hash by just copying whatever the current fetch
produces without separately verifying that content is actually what was
intended -- the hash pins against silent *future* drift, but doesn't by
itself verify the *current* content is correct; combine hash-pinning
with an actual review of what's being fetched. Also don't leave any
dependency in the graph unpinned "because it's small" or "unlikely to
change" -- the whole value of reproducible builds depends on there being
no exceptions.

## Verify

Fetch the pinned dependency fresh in a clean environment and confirm the
`sha256` hash matches what's declared, failing loudly if it doesn't.
Re-run the build after pinning and confirm behavior is now stable and
reproducible across repeated fetches, including from a completely clean
Bazel cache/fetch state.
