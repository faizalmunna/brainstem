---
name: macro-vs-rule-confusion-breaks-composability
description: A Bazel macro is used where a proper custom rule was needed, causing the resulting targets to behave unexpectedly under queries, visibility checks, or dependency analysis.
triggers: ["bazel macro not showing up in query", "bazel macro visibility not working as expected", "macro vs rule confusion bazel", "bazel macro breaks dependency graph analysis"]
permissions: ["READ"]
---

## Symptom

A Bazel macro that generates multiple targets works fine for basic
building, but something built on top of it breaks unexpectedly --
`bazel query` doesn't show an intermediate target that other code
expected to reference directly, visibility enforcement doesn't behave as
expected for the macro's generated targets, or the macro's expansion
happens at the wrong time relative to configuration/analysis phases.

## Likely causes

- **A macro (a plain Starlark function generating a set of `native.*` or
  rule calls) was used for something that actually needed a custom rule**
  -- macros expand purely at the loading phase, before Bazel's analysis
  phase, so anything that needs to participate in the analysis-phase
  dependency graph as a first-class node (proper providers, aspects,
  configuration-dependent behavior) can't be implemented correctly as a
  pure macro.
- **A macro's internal, intermediate targets weren't intended to be
  depended on directly by other code**, but something outside the macro
  started referencing one of those internal target names directly,
  coupling to an implementation detail that could change if the macro's
  internals are refactored.
- **Symbolic macros (a newer Bazel feature providing better encapsulation
  than legacy macros) weren't used where they would have prevented this
  exact class of problem**, if the Bazel version in use supports them and
  the team simply hadn't adopted them yet.
- **A macro generates target names based on a naming convention that
  isn't documented/guaranteed**, so other code depending on those
  generated names is fragile to a macro implementation change that
  preserves behavior but changes naming.

## Diagnose

1. Determine whether the problematic construct is a legacy macro (a
   plain Starlark function) or a proper custom rule, by reading its
   definition -- a macro directly calls other rules/macros, while a rule
   is defined via `rule()` with an implementation function receiving a
   `ctx`.
2. Identify exactly what capability is missing/broken -- if it's about
   analysis-phase behavior (providers, aspects, build-configuration-
   dependent logic), a macro is fundamentally insufficient regardless of
   how it's tweaked.
3. Check what other code depends on the macro's generated intermediate
   target names, and whether that dependency was intentional (a
   documented, stable public target) or an accidental coupling to an
   implementation detail.
4. Check the Bazel version in use for whether symbolic macros are
   available, if better encapsulation would solve the specific problem.

## Fix

Convert the macro to a proper custom rule (or use symbolic macros, if
available and sufficient) when the underlying need is genuinely
analysis-phase behavior -- participating properly in providers, aspects,
or configuration-dependent logic. For a macro whose generated
intermediate targets are being depended on unintentionally, either make
those targets genuinely public and documented (if that's actually a
reasonable, supported use case) or use naming/visibility conventions
that clearly mark them as private implementation details not meant to be
depended on directly.

## Pitfalls

Don't reach for ever-more-elaborate macro tricks to work around a
fundamental macro-vs-rule capability gap -- if the actual need is
analysis-phase participation, a proper rule is the correct tool, and
continuing to patch a macro to simulate rule-like behavior produces
fragile, hard-to-maintain Starlark code.

## Verify

After converting to a proper rule (or fixing the encapsulation issue),
confirm the previously broken query/visibility/dependency-graph behavior
now works as expected, and confirm any legitimate external consumers of
the target(s) still work correctly against the new implementation.
