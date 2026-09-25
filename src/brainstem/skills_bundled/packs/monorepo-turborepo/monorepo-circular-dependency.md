---
name: monorepo-circular-dependency
description: Detect and resolve a circular dependency between packages in a monorepo before it causes confusing build-order failures or forces awkward workarounds.
triggers: ["circular dependency monorepo", "package a depends on package b depends on package a", "circular import monorepo", "cannot determine build order"]
permissions: ["READ"]
---

## Symptom
A monorepo's build tool reports it can't determine a build order (or
silently produces an inconsistent one), or two-plus packages import from
each other in a way that only "works" by accident of module resolution
timing -- often surfacing as `undefined` values for something that should
be defined, or a build tool error naming a cycle explicitly.

## Likely causes
1. **Two packages genuinely need functionality from each other** because
   a piece of shared logic was placed in whichever package happened to
   need it first, and later a change in the other direction was added
   without noticing it created a cycle.
2. **A "shared utilities" package accumulated a dependency back on a
   feature-specific package** (utils importing something from an app-
   level package) that should have stayed one-directional (feature
   packages depend on shared utils, never the reverse).
3. **Type-only circular imports** (TypeScript types referencing each
   other across packages) that work fine for type-checking but still
   register as a structural cycle in the build/dependency graph tooling,
   which may or may not distinguish type-only cycles from runtime ones.
4. **An indirect cycle through three or more packages** (A -> B -> C ->
   A) that's harder to spot than a direct two-package cycle, especially
   as a monorepo grows and no single person has the full dependency graph
   in their head.

## Diagnose
- Use the build tool's graph visualization (`nx graph`, `turbo run build
  --graph`, or a dedicated dependency-cycle-detection lint rule) to find
  the cycle explicitly rather than trying to trace imports by hand across
  many packages.
- For each edge in the reported cycle, identify what's actually being
  imported across it -- a specific type, a specific utility function --
  to understand what would need to move to break the cycle.
- Distinguish a type-only cycle (may be acceptable/unavoidable in some
  type systems without runtime implications) from a genuine runtime
  circular import (which can cause real initialization-order bugs, not
  just tooling complaints).

## Fix
- **Extract the shared piece into a new, lower-level package** that both
  original packages depend on, removing the direct edge between them --
  the most common and generally cleanest fix for a genuine two-way need.
- **Move the misplaced dependency to the correct direction** when the
  cycle was actually a "utils package started depending on something it
  shouldn't" mistake -- relocate that specific piece of logic to where it
  belongs in the intended one-directional hierarchy.
- **Use dependency inversion** (define an interface/type in the
  lower-level package, implement it in the higher-level one, pass the
  implementation in rather than importing it directly) when the
  dependency is fundamentally about behavior the lower-level package
  needs to call but shouldn't own.
- For an indirect multi-package cycle, resolve one edge at a time
  (usually the "newest" or most obviously misplaced one) and re-check the
  graph, rather than trying to redesign the whole chain at once.

## Pitfalls
- Working around a cycle with dynamic/lazy imports (deferring the import
  until runtime to dodge a build-time cycle error) can make the tooling
  stop complaining while leaving the actual architectural problem (and
  potential runtime initialization-order fragility) in place.
- Extracting a new shared package for every two-package cycle without
  considering whether the logic genuinely belongs together can lead to a
  proliferation of tiny, oddly-scoped packages -- consider whether the
  cycle is a sign the two packages' boundaries are drawn wrong entirely,
  not just that a shared package is needed.

## Verify
Re-run the dependency graph visualization/cycle-detection tool after the
fix and confirm the specific cycle no longer appears, and confirm the
build tool can now compute a consistent, deterministic build order for
all previously-involved packages.
