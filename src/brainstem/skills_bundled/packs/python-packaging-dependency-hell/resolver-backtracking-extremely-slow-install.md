---
name: resolver-backtracking-extremely-slow-install
description: A pip or other Python dependency resolver install takes an extremely long time or appears to hang because the resolver is backtracking through many incompatible version combinations.
triggers: ["pip install taking forever", "dependency resolver hanging", "pip backtracking slow", "python install stuck resolving dependencies"]
permissions: ["READ"]
---

## Symptom

Running `pip install` (or a similar resolver-based install command) for
a project's dependencies takes minutes to tens of minutes, or appears to
hang entirely, with no clear error -- the resolver is silently working
through a large search space of version combinations trying to find one
that satisfies every declared constraint.

## Likely causes

- **Two or more dependencies have version constraints that are difficult
  to jointly satisfy**, forcing the resolver to backtrack repeatedly --
  trying a version of package A, finding it conflicts with a constraint
  from package B, trying a different version of A, and so on across a
  large combinatorial space.
- **A dependency's constraint is looser than necessary** (an unbounded or
  very wide version range) which increases the number of candidate
  versions the resolver has to consider and potentially reject one by
  one.
- **A new version of a package was just published that changes its own
  dependency constraints**, shifting what combinations are valid and
  triggering a resolver process that used to be fast to suddenly need to
  search much more broadly.
- **The resolver has to fetch metadata for many candidate versions from
  the package index over the network**, and slow network conditions
  compound with the backtracking search, making an already slow logical
  process also slow due to I/O.

## Diagnose

1. Run the install with verbose resolver output enabled (pip supports
   `-v`/`-vv`, or resolver-specific debug flags) to see which specific
   packages/constraints the resolver is backtracking on.
2. Identify the specific pair or set of packages whose constraints are in
   tension, by reading the verbose output for repeated consideration of
   the same packages.
3. Check whether a recently published version of any dependency changed
   its own constraints, by comparing the dependency's changelog/release
   history around when the slowdown started.
4. Time how much of the delay is network-bound (fetching package
   metadata) versus CPU-bound (pure resolver computation) to determine
   where the bottleneck actually is.

## Fix

Tighten overly loose version constraints in the project's own
dependency declarations to reduce the resolver's search space, based on
what's actually tested/supported rather than leaving them maximally
open. For a specific identified conflicting pair, either pin one side to
a version known to be compatible, or use a dependency-resolution report
to understand exactly which upstream constraint is the source of tension
and consider whether an alternative package/version avoids it. Use a
lock file (via a tool that generates one, like `pip-tools`, `poetry`, or
`uv`) so the expensive resolution only has to happen once, with
subsequent installs using the pre-resolved lock file directly rather than
re-running the full resolver every time.

## Pitfalls

Don't pin every dependency to an exact version reflexively to avoid ever
triggering resolver backtracking -- that trades resolution speed for
losing the ability to pick up compatible patch/minor updates
automatically, and can itself create a different maintenance burden
(manually bumping every pin). Use a lock file mechanism that separates
"declared, flexible constraints" from "resolved, pinned versions" rather
than making every declaration maximally rigid.

## Verify

Re-run the install after tightening constraints or adopting a lock file
and measure the actual time to complete, confirming it's now fast and
predictable. Confirm the resolved dependency set still satisfies the
project's actual runtime requirements (run the test suite against the
newly resolved versions) rather than just checking that resolution
completed quickly.
