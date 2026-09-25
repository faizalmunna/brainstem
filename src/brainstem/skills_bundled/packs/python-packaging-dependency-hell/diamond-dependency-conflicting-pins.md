---
name: diamond-dependency-conflicting-pins
description: Two of a project's direct dependencies require incompatible versions of a shared transitive dependency, making it impossible to satisfy both without upgrading, forking, or vendoring something.
triggers: ["conflicting dependency requirements", "diamond dependency problem python", "two packages need different versions of same library", "resolver cannot find compatible version"]
permissions: ["READ"]
---

## Symptom

A dependency resolver reports it cannot find a set of package versions
that satisfies all constraints, with an error identifying two (or more)
of the project's direct dependencies that each require a different,
mutually incompatible version range of the same shared transitive
dependency -- a classic "diamond dependency" conflict.

## Likely causes

- **One direct dependency hasn't been updated in a while and still
  pins/requires an old version of the shared transitive dependency**,
  while a different, more actively maintained direct dependency requires
  a newer version, and their ranges don't overlap.
- **A direct dependency was recently upgraded**, and its new version
  introduced a tighter or different constraint on the shared transitive
  dependency than before, newly creating a conflict that didn't exist
  with the previous version.
- **The project itself has an unnecessarily tight pin on the shared
  transitive dependency** (perhaps added defensively at some point) that
  neither direct dependency actually requires that specifically, but
  which now conflicts with one of them.
- **Two unrelated features of the project each pulled in a different
  library that happens to share a common, incompatible transitive
  dependency**, and the conflict was never noticed until both were
  installed together for the first time.

## Diagnose

1. Read the resolver's error output carefully -- modern resolvers
   (`pip`'s newer resolver, `poetry`, `uv`) report exactly which two
   packages and which version ranges are in conflict, rather than a
   generic failure.
2. Check each conflicting direct dependency's actual current release
   history for whether a newer version relaxes or changes its
   constraint on the shared transitive dependency.
3. Determine whether the project's own explicit dependency
   declarations include an unnecessary pin on the transitive dependency
   that's contributing to the conflict.
4. Check whether either conflicting direct dependency is genuinely
   necessary, or whether an alternative library serving the same purpose
   without the conflicting transitive dependency exists.

## Fix

Upgrade whichever direct dependency has the older, more restrictive
constraint to a newer version that's compatible with the other's
requirement, if such a version exists. If the project has an
unnecessary explicit pin on the transitive dependency contributing to
the conflict, remove or relax it. If no compatible version combination
exists at all, consider replacing one of the conflicting direct
dependencies with an alternative library, or as a last resort,
vendoring/forking a patched version of the transitive dependency with a
relaxed constraint (understood as a genuine maintenance burden, not a
casual choice).

## Pitfalls

Don't force-install an incompatible combination by disabling dependency
resolution checks (installing with flags that skip conflict detection)
-- that doesn't resolve the actual conflict, it just hides it, and the
resulting environment may have subtly broken behavior from the
transitive dependency being at a version one of the direct dependencies
wasn't actually tested against.

## Verify

After resolving the conflict (upgrade, pin adjustment, or dependency
replacement), run the project's full test suite against the newly
resolved dependency set to confirm nothing broke as a side effect of
whichever change was made, not just that the resolver itself succeeded.
