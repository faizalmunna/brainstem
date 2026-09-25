---
name: query-language-overbroad-target-pattern
description: A Bazel query or build command using a broad target pattern (like //...) unexpectedly builds or affects far more targets than intended, wasting time or catching unrelated targets in a CI gate.
triggers: ["bazel build wildcard too broad", "bazel query matching too many targets", "ci building unrelated targets bazel", "bazel target pattern unintended scope"]
permissions: ["READ"]
---

## Symptom

Running a Bazel command with a target pattern intended to scope to a
specific area of the repository (a wildcard like `//services/...` or a
query expression) ends up building, testing, or otherwise affecting far
more targets than intended -- either wasting significant CI time, or
worse, causing an unrelated team's targets to be included in a gate they
shouldn't be subject to.

## Likely causes

- **A wildcard pattern (`//...` or a broad subtree wildcard) was used
  without realizing how many targets actually exist under that path** in
  a large, growing monorepo, especially if the pattern was written early
  in the repository's life when the subtree was much smaller.
- **A query using dependency operators (`deps()`, `rdeps()`) was scoped
  too broadly** (an unbounded universe scope, or a starting point higher
  in the dependency graph than intended), pulling in a much larger set
  of targets than the specific relationship the query was meant to
  express.
- **A CI configuration's target pattern was copy-pasted from a broader
  context** (a top-level CI job's pattern reused for a more specific,
  intended-to-be-narrower job) without actually narrowing it for the new
  job's specific purpose.
- **New targets were added under a wildcard's scope by other teams over
  time**, and a pattern that was appropriately scoped when written
  gradually became broader in practice as the repository grew, without
  anyone revisiting it.

## Diagnose

1. Run the exact target pattern through `bazel query` (without actually
   building/testing) to see the full list of targets it resolves to, and
   compare against what was actually intended.
2. For a query-based pattern, check the specified universe scope and
   query operators against the actual intended relationship, testing
   incrementally with narrower scopes to see where the pattern starts
   matching more than expected.
3. Check CI job configuration history for whether the current pattern
   was copy-pasted from a different, broader-purpose job.
4. Check whether the affected subtree's target count has grown
   significantly since the pattern was originally written, using version
   control history on the relevant `BUILD` files as a proxy.

## Fix

Narrow target patterns to precisely the intended scope, using more
specific paths or explicit target lists rather than broad wildcards
where precision matters (particularly for CI gates that should only
apply to a specific team/area). For query-based patterns, scope the
universe explicitly rather than relying on defaults that might be wider
than intended. Where a CI job's pattern needs to stay broad
intentionally (a genuine full-repo check), document that intent clearly
so it's not mistaken for an oversight later, and distinguish it from
narrower, team/area-scoped jobs that should use precise patterns.

## Pitfalls

Don't fix an overbroad pattern by excluding specific known-problematic
targets one at a time (`//... - //path/to:target`) as new instances of
the problem show up -- that's a growing, fragile exclusion list rather
than an actually correctly-scoped pattern; fix the pattern's scope
directly instead.

## Verify

Run the corrected target pattern through `bazel query` and confirm the
resolved target list matches exactly the intended scope. Run the actual
CI job with the corrected pattern and confirm build/test time drops
proportionally to the reduced scope, and confirm no previously-affected
unrelated team's targets show up in the job's results anymore.
