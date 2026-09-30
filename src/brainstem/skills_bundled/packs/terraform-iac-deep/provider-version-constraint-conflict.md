---
name: provider-version-constraint-conflict
description: Terraform init fails or resolves an unexpected provider version because multiple modules declare incompatible version constraints for the same provider.
triggers: ["terraform init version constraint error", "no compatible provider version found", "terraform provider requirement conflict", "different modules require different provider versions", "terraform init failed to resolve provider version"]
permissions: ["READ"]
---

## Symptom
`terraform init` fails outright with an error like "no available
releases match" or "Failed to query available provider packages" citing
conflicting version constraints from different modules, or -- more
insidiously -- `init` succeeds but resolves to a provider version nobody
explicitly chose because it's the only one satisfying every module's
`required_providers` constraint simultaneously, and that version behaves
differently than any individual module's author tested against.

## Likely causes
1. **The root module and one or more child modules each declare their
   own `required_providers` version constraint independently**, written
   at different times against different provider releases, and as the
   dependency tree grows (especially with third-party/community modules
   pinned to old constraints), the intersection of all constraints
   narrows or becomes empty.
2. **A newly added module (often a third-party one from the registry)
   pins a narrow or outdated upper bound** (e.g. `< 4.0`) that conflicts
   with the rest of the codebase already standardized on a newer major
   version, so adding that one module breaks provider resolution for
   everything else that shares the same provider.
3. **The committed `.terraform.lock.hcl` was generated against a
   different set of modules/constraints than currently declared** (e.g.
   after removing a module that had a wide constraint, or adding one with
   a narrow one) and wasn't regenerated, so `init` without `-upgrade`
   tries to reuse a lockfile entry that no longer satisfies the current
   constraint set.
4. **Version constraints are specified inconsistently in style** across
   modules (`>=`, `~>`, exact pins) without a team convention, making it
   hard for any single author to predict how their module's constraint
   will interact with others when combined, versus deliberately choosing
   compatible ranges.

## Diagnose
- Read the exact `terraform init` error message -- it typically lists
  each module's source and its specific version constraint for the
  conflicting provider, giving a direct map of which modules are
  incompatible rather than requiring a manual search.
- Grep the entire module tree (root plus every vendored/child module
  actually in use) for `required_providers` blocks referencing the
  provider in question, and tabulate each one's constraint string side by
  side to see exactly where the intersection breaks.
- Run `terraform init -upgrade` in a scratch/throwaway copy of the
  config to see what version (if any) it resolves to when allowed to
  pick freely, versus what's currently pinned in `.terraform.lock.hcl` --
  a large gap suggests the lockfile is stale relative to current
  constraints.
- For a third-party registry module, check its own repository/changelog
  for whether a newer version of that module has already relaxed its
  provider constraint -- the fix is often "bump the module," not "fight
  the provider version."

## Fix
Standardize provider version constraints across the codebase using a
consistent, deliberately chosen range (typically `~>` pinned to a minor
version) declared in every module's `required_providers` block, and
prefer updating an outdated third-party module to a newer release (which
usually widens its own constraint) over trying to force compatibility by
loosening constraints ad hoc in the codebase's own modules. When a
genuinely irreconcilable conflict exists between two required modules,
treat it as a real architectural decision -- vendor and patch the
conflicting module's constraint deliberately (with a comment explaining
why), or replace it with an alternative module/resource, rather than
picking whichever constraint happens to compile today.

## Pitfalls
- Deleting or drastically widening a constraint (e.g. removing the upper
  bound entirely) just to make `init` succeed reopens the
  provider-upgrade-silent-behavior-change failure mode -- an unconstrained
  provider version can float to a new major release on the next `init
  -upgrade` with no review.
- Regenerating `.terraform.lock.hcl` from scratch to "fix" a conflict
  without understanding why the previous lockfile no longer satisfied
  constraints can mask a real incompatibility between two modules that
  will resurface the next time either module's constraint changes.

## Verify
Run `terraform init` from a clean state (remove `.terraform` and rerun,
not just reuse a cached provider plugin directory) and confirm it
succeeds with a single resolved provider version that satisfies every
module's declared constraint, then check `.terraform.lock.hcl` to confirm
the resolved version is the one intended and commit it so every other
environment resolves identically.
