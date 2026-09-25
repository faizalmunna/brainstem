---
name: remote-cache-miss-despite-unchanged-inputs
description: Bazel's remote build cache misses repeatedly for a target even though its declared inputs haven't changed, forcing unnecessary rebuilds.
triggers: ["bazel remote cache not hitting", "bazel rebuilding unchanged target", "remote cache miss unchanged inputs", "bazel cache key not stable"]
permissions: ["READ"]
---

## Symptom

A Bazel target that should be cacheable (its source files and
declared dependencies haven't changed since the last successful build)
still misses the remote cache and gets rebuilt from scratch, wasting
build time that the remote cache was specifically adopted to save.

## Likely causes

- **The target's action includes an input that varies between runs
  even when logically "the same"** -- an embedded timestamp, a
  non-deterministic environment variable captured into the action's
  command line, or a file path that differs between machines (an
  absolute path leaking into the cache key instead of a relative one).
- **A build flag or environment variable that affects the action's cache
  key changes between invocations** (different `--define` values,
  different toolchain versions resolved based on host state) without
  the team realizing that flag affects cacheability.
- **The action isn't actually deterministic** -- the same inputs produce
  different byte-for-byte outputs across runs (a compiler embedding a
  build ID, a code generator using non-reproducible ordering), which
  Bazel's cache validation can detect and correctly refuse to reuse.
- **Different CI runners or developer machines are on different Bazel
  versions, or different toolchain versions resolved from the host**,
  causing cache keys computed on one machine to never match cache
  entries written by another.

## Diagnose

1. Use Bazel's `--experimental_remote_cache_compression` and cache-
   related debugging flags (e.g. comparing action digests via `bazel
   aquery` or examining the action's exact command line) to identify
   exactly what's varying between two runs that should produce identical
   cache keys.
2. Compare Bazel version, toolchain versions, and relevant `--define`/
   flag values across the environments experiencing cache misses.
3. Check the target's rule definition and any wrapped tools for known
   non-determinism sources (embedded timestamps, absolute paths, unstable
   iteration order in generated output).
4. Test cacheability directly by running the exact same build twice on
   the exact same machine with the same flags -- if it cache-hits on
   repeat runs on one machine but misses cross-machine, the issue is
   environment-dependent cache-key variation, not fundamental non-
   determinism in the action itself.

## Fix

Eliminate non-deterministic inputs to cacheable actions -- strip
timestamps from generated output where possible, use relative paths
consistently rather than absolute host paths, and pin build flags and
toolchain versions explicitly (via `.bazelrc` and toolchain
registration) so they're consistent across every machine and CI runner
rather than resolved differently per-host. Standardize the Bazel version
and toolchain versions across all environments that need to share a
remote cache. For actions with genuine, unavoidable non-determinism,
accept they won't reliably cache-hit and consider whether that
non-determinism itself should be fixed at the source (the tool/generator
producing it) for other reasons beyond caching.

## Pitfalls

Don't disable remote caching for a problematic target as a quick fix to
avoid "wasted" cache-miss overhead -- that gives up caching entirely for
that target rather than fixing the actual determinism/consistency issue,
and the same target likely still rebuilds unnecessarily locally too.
Investigate and fix the root cause instead.

## Verify

After fixing identified non-determinism/environment variation sources,
run the same build from two different machines/CI runners with a clean
local cache and confirm the second one hits the remote cache populated
by the first, for the specific previously-problematic target.
