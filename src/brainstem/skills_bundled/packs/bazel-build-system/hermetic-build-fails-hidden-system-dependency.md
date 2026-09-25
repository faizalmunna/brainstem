---
name: hermetic-build-fails-hidden-system-dependency
description: A Bazel build passes on one machine but fails on another because it implicitly depends on a tool or file from the host system that isn't declared as a build dependency.
triggers: ["bazel build works locally fails ci", "bazel not hermetic system dependency", "build passes one machine fails another", "bazel implicit system tool dependency"]
permissions: ["READ"]
---

## Symptom

A Bazel build succeeds on a developer's machine (or one CI runner image)
but fails on a different machine or CI runner with an error about a
missing tool, missing file, or unexpected version behavior -- despite
Bazel's whole premise being that builds are hermetic and reproducible
regardless of the host environment.

## Likely causes

- **A `genrule` or custom build rule shells out to a tool assumed to be on
  `PATH`** (a system compiler, a scripting language interpreter, an image
  processing tool) without declaring it as a Bazel toolchain or explicit
  dependency, so the build silently relies on whatever happens to be
  installed on the host rather than a hermetic, declared version.
- **A build rule reads a file from an absolute host path** (a system
  config file, a certificate store) instead of treating it as a proper
  Bazel input, working only on machines where that file happens to exist
  at that specific location.
- **The build was tested only on a single, consistently-configured
  machine/image** (a developer's own laptop, a single CI runner
  configuration) where the hidden dependency happens to always be
  present, so the non-hermeticity was never surfaced until a genuinely
  different environment was used.
- **A toolchain was registered but its resolution silently falls back to
  a host-detected tool when the declared one isn't found**, masking the
  dependency gap in environments where a compatible fallback happens to
  exist.

## Diagnose

1. Reproduce the failure and read the exact error to identify the
   specific missing tool, file, or version mismatch.
2. Search the relevant `BUILD`/`.bzl` files for any `genrule`, `sh_binary`,
   or custom rule that shells out to a command, and check whether that
   command is provided via a declared Bazel toolchain/dependency or
   assumed to exist on `PATH`.
3. Check for any absolute host filesystem paths referenced in build
   rules, which is a direct sign of a non-hermetic dependency.
4. Compare the environment where the build succeeds against where it
   fails (installed tool versions, available system packages) to
   pinpoint exactly what's present in one and not the other.

## Fix

Declare every external tool a build rule depends on as a proper Bazel
toolchain or a `http_archive`/`http_file`-fetched dependency pinned to a
specific version, rather than relying on whatever's installed on the
host machine. Replace absolute host filesystem path references with
proper Bazel-managed inputs (declared as `srcs`/`data` in the relevant
target). Use Bazel's toolchain resolution mechanism deliberately
(registering toolchains explicitly) rather than relying on implicit
host-tool fallback behavior that can mask hermeticity gaps.

## Pitfalls

Don't fix a single missing-tool failure by just installing that tool on
the failing CI runner's image -- that "fixes" the symptom for that one
runner while leaving the underlying non-hermetic dependency in place for
the next new environment (a different CI runner, a new developer's
machine) to rediscover. Fix the build rule to declare its dependency
properly instead.

## Verify

Run the build in a deliberately minimal/different environment (a fresh
container image with only Bazel and the declared toolchains, nothing
else pre-installed) and confirm it succeeds without needing anything
beyond what's explicitly declared. Use Bazel's sandboxing features
(enabled by default in most configurations) to help catch non-hermetic
access during local development, not just in CI.
