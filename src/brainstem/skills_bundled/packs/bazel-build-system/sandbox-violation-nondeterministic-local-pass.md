---
name: sandbox-violation-nondeterministic-local-pass
description: A Bazel build passes locally with sandboxing disabled but fails in CI or for other developers because it silently depends on a file outside its declared inputs.
triggers: ["bazel build passes locally fails ci sandbox", "bazel sandbox violation", "works without sandbox fails with sandbox", "bazel undeclared input dependency"]
permissions: ["READ"]
---

## Symptom

A Bazel target builds successfully on a developer's machine (often
because sandboxing was disabled, running in a mode that tolerates
undeclared file access, or simply happened to have the needed file
present in the workspace already) but fails in CI or for other
developers with a "file not found" error for a file that was never
declared as one of the target's inputs.

## Likely causes

- **The build action reads a file from the workspace directory that
  happens to be present but was never declared in `srcs` or `data`**,
  and Bazel's sandbox (when enabled) correctly restricts the action to
  only its declared inputs, exposing the gap that an unsandboxed or
  loosely-configured local build tolerated.
- **A tool invoked by the build rule has its own implicit search path
  behavior** (looking for a config file in a parent directory, checking
  environment-specific locations) that finds something in a developer's
  full workspace checkout but wouldn't find it in a properly sandboxed,
  minimal input set.
- **Sandboxing was disabled or weakened in local development
  configuration** (a `.bazelrc` override, a flag commonly used to work
  around a different, unrelated sandboxing friction) masking this class
  of issue during normal local development, only surfacing in a stricter
  CI configuration.
- **A previous build action left behind an output file that a later
  action implicitly depends on** without that dependency being declared,
  working by accident when builds happen to run in a particular order or
  reuse of build state.

## Diagnose

1. Reproduce the failure with Bazel's sandboxing explicitly enabled
   locally (`--spawn_strategy=sandboxed` or the equivalent default,
   confirming any local override that disables it is temporarily
   removed) to see the same failure locally that CI experiences.
2. Read the exact error for which specific file is missing, and trace
   which build action was trying to access it.
3. Check the target's `BUILD` file for whether that file is declared as
   a `src`, `data` dependency, or is expected to come from another
   target's output that isn't declared as a dependency.
4. Check whether any local `.bazelrc` or personal configuration disables
   or weakens sandboxing in a way that would mask this class of issue
   during normal local development.

## Fix

Declare every file an action actually needs as an explicit input
(`srcs`, `data`, or a proper target dependency) rather than relying on
implicit filesystem access that happens to work when sandboxing is
disabled or weak. Remove any local configuration that disables
sandboxing for convenience, since it actively hides exactly this class of
bug until it surfaces in a stricter environment (CI, another developer's
machine) at a less convenient time. If a tool has its own implicit
search-path behavior that can't be fully declared, wrap it in a way that
makes its actual file access explicit and controllable (passing an
explicit config path rather than relying on search-path discovery).

## Pitfalls

Don't treat sandboxing as an annoyance to work around locally -- it's
specifically there to catch this exact class of bug before it reaches CI
or another developer's machine; disabling it locally trades short-term
convenience for exactly the kind of failure this skill addresses.

## Verify

Run the previously-failing target with sandboxing enabled and confirm it
now succeeds, having declared all its actual dependencies explicitly.
Run a clean build from a fresh checkout (simulating a new developer or
CI environment) to confirm no residual implicit dependency on
pre-existing workspace state remains.
