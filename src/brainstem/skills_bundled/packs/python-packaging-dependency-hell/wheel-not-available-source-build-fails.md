---
name: wheel-not-available-source-build-fails
description: Installing a Python package fails because no pre-built wheel is available for the target platform/Python version, and building from source fails due to missing system dependencies.
triggers: ["pip install failed building wheel", "no matching distribution found", "source build failed missing compiler", "python package build from source error"]
permissions: ["READ"]
---

## Symptom

`pip install` for a package (often one with C/C++/Rust extensions) fails
with an error about building a wheel from source -- either because no
pre-built wheel exists for the exact combination of operating system,
architecture, and Python version being used, or because the source build
itself fails due to a missing compiler or system library.

## Likely causes

- **The package doesn't publish a pre-built wheel for the specific
  platform/architecture/Python version combination in use** (a newer
  Python version the package hasn't published wheels for yet, an
  uncommon architecture like ARM on a platform where the package mainly
  targets x86), forcing a source build that many environments aren't
  set up to perform.
- **The source build requires a C/C++ compiler or build toolchain that
  isn't installed** on the target machine (common in minimal container
  images, CI runners stripped down for size, or a developer's fresh
  machine without build tools installed).
- **The source build requires a specific system library's headers**
  (development package, not just the runtime library) that isn't
  installed, distinct from the compiler itself -- a common gap in
  minimal Docker base images.
- **A version pin in the project's requirements is older than what has
  wheels available for the current Python version**, forcing a source
  build for a version that was actually built with wheels for the
  Python version the pin was originally written against.

## Diagnose

1. Read the exact error message for whether it's "no matching
   distribution" (no wheel found, and no source fallback attempted) or a
   source-build compilation failure (with a specific missing compiler/
   header error).
2. Check the package's published wheel availability (on PyPI, via its
   file listing) for the exact platform/architecture/Python version in
   use, to confirm whether a wheel genuinely doesn't exist versus a local
   environment/index configuration issue preventing it from being found.
3. For a compilation failure, read the specific error for exactly which
   compiler or header file is missing.
4. Check whether upgrading the pinned version of the failing package
   would pick up a version with wheel support for the current
   environment.

## Fix

Where possible, upgrade the pinned dependency version to one that
publishes a wheel for the target environment, which is usually the
simplest fix and avoids needing any build toolchain at all. Where a
source build is genuinely necessary (no wheel exists for a required
older version, or for an internal/private package), install the required
compiler and development headers explicitly as part of the environment
setup (in a Dockerfile, a CI setup step, documented onboarding steps)
rather than assuming they're present. For container-based environments,
consider a multi-stage build that includes build tools only in a
build-time image layer, keeping the final runtime image minimal while
still supporting the source build step where it happens.

## Pitfalls

Don't add a full build toolchain to a production runtime container image
just to satisfy a source build at install time -- build in a separate
stage/image and copy only the resulting installed package into the
final, minimal runtime image, to avoid bloating the deployed image with
build tools that aren't needed at runtime. Also don't pin to an old
package version purely to avoid a build issue without checking whether
that old version has other known issues (security, bugs) that matter
more than the build inconvenience.

## Verify

Re-run the install in a clean environment matching the actual target
deployment (same OS, architecture, Python version, container base image)
and confirm it succeeds without requiring manual intervention. If a
build toolchain was added, confirm the final runtime image (if using
multi-stage builds) doesn't retain unnecessary build-time bloat.
