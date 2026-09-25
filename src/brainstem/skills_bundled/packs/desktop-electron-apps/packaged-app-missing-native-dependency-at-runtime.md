---
name: packaged-app-missing-native-dependency-at-runtime
description: An Electron application works correctly in development but crashes or fails to start after packaging because a native Node.js module wasn't correctly bundled or rebuilt for the target platform.
triggers: ["electron packaged app crashes native module", "works in dev fails when packaged", "native module not found after build", "electron app wont start after packaging"]
permissions: ["READ"]
---

## Symptom

An Electron application runs correctly when launched via the development
command (`electron .` or similar) but crashes on startup, or fails when
a specific feature is used, once packaged into a distributable
installer -- typically with an error about a missing native module or an
architecture mismatch.

## Likely causes

- **A native Node.js module (a module with a compiled `.node` binary
  addon) wasn't correctly rebuilt against Electron's specific Node.js/
  V8 ABI version** -- native modules must be compiled against the exact
  runtime they'll execute in, and Electron bundles its own Node.js
  version that can differ from the system Node.js used during
  development.
- **The packaging tool's configuration doesn't correctly include the
  native module's compiled binary** for the target platform/architecture
  in the final package, even though it's present in the development
  `node_modules` folder.
- **A native module was built for the wrong target architecture**
  (building for x64 when packaging for arm64, or vice versa, common when
  cross-compiling for a different platform than the build machine), so
  the binary exists in the package but isn't compatible with the actual
  runtime CPU architecture.
- **A dependency's native module wasn't declared correctly as needing
  rebuild for Electron** in the project's build configuration, so the
  packaging/rebuild step skipped it, leaving the system-Node-compiled
  version bundled instead.

## Diagnose

1. Reproduce the failure by running the packaged application (not the
   dev-mode command) and capture the exact error message, which usually
   names the specific failing native module.
2. Check whether the project's build process includes an explicit
   Electron-specific native module rebuild step (via tools like
   `electron-rebuild` or the packaging tool's built-in equivalent).
3. Inspect the actual packaged application's contents for the specific
   native module's compiled binary and confirm its target architecture
   matches the platform being packaged for.
4. Compare the Node.js ABI version Electron uses (per the specific
   Electron version) against what the native module was actually
   compiled against.

## Fix

Ensure the build/packaging pipeline explicitly rebuilds every native
module against Electron's Node.js ABI (using `electron-rebuild` or the
packaging tool's equivalent mechanism) as a required step before
packaging, not relying on whatever was compiled during a plain `npm
install` for system Node.js. For multi-architecture distribution
(building for arm64 from an x64 machine, for instance), ensure the
rebuild step targets the correct output architecture explicitly rather
than defaulting to the build machine's native architecture.

## Pitfalls

Don't work around a native module rebuild issue by pinning to an older
Electron version indefinitely just to match whatever the module happened
to work with -- that trades a build-configuration fix for accumulating
Electron version debt; fix the rebuild step properly instead.

## Verify

Build a fresh package from a clean environment (deleting `node_modules`
and reinstalling, to avoid any stale locally-rebuilt artifacts masking
the issue) and confirm the packaged application launches and the
specific previously-failing feature works correctly on the actual target
platform/architecture, not just the development machine.
