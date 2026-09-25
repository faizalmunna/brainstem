---
name: race-detector-flags-load-only-race
description: Investigate a data race that the Go race detector or production symptoms only surface under real concurrent traffic, never in normal unit test runs.
triggers: ["race condition only in production", "race detector clean in tests but crashes in prod", "concurrent map read write panic under load", "data race only under real traffic", "intermittent corruption high concurrency"]
permissions: ["READ"]
---

## Symptom
Unit tests pass, and even `go test -race` on the existing test suite reports
nothing -- but production, under real concurrent traffic, occasionally
crashes with `fatal error: concurrent map read and map write`, corrupts
shared state, or produces obviously wrong output (a counter that doesn't
add up, a struct with fields from two different requests mixed together).
The race is real but the test suite's concurrency level and code paths never
exercise the interleaving that triggers it.

## Likely causes
1. **The race detector can only report races it actually observes during
   execution** -- it's not a static analyzer, so a race in a code path the
   test suite never calls concurrently (only ever called from a single
   goroutine in tests, but called from multiple request-handling goroutines
   in production) is invisible to `-race` no matter how long the tests run.
2. **Shared mutable state accessed without synchronization** -- a package-
   level variable, a struct field on a singleton/shared service instance, or
   a captured loop variable/closure shared across goroutines, read and
   written without a mutex or atomic, where the race window is small enough
   that it rarely aligns in a lightly concurrent test but reliably aligns
   under production's higher concurrency and longer running time.
3. **A map or slice shared across goroutines with concurrent reads and
   writes** (maps are explicitly not safe for concurrent read+write in Go;
   a build with the race detector can crash the process outright on this
   specific case even outside of `-race` test runs, via a runtime check) --
   again, only reliably observed when concurrency is high enough.
4. **A "lazy init" / cache pattern** (`if cache == nil { cache = compute() }`)
   done without a `sync.Once` or lock, assumed safe because it's "just a
   read-mostly cache" -- under concurrent first-access, multiple goroutines
   can race on the nil check and the write.

## Diagnose
- Don't conclude "no race" from a clean `-race` run on the existing test
  suite alone -- specifically write a targeted concurrency test that spins
  up N goroutines (N large enough to exceed `GOMAXPROCS`, e.g. 50-100) all
  hitting the suspected shared-state code path simultaneously, and run *that*
  under `go test -race -count=10`.
- Grep the suspected package for package-level `var` declarations that are
  mutable (not `const`, not written-once-at-init) and check every place they're
  read or written for a mutex/atomic guarding it.
- Grep for map or slice fields on any struct that is constructed once and
  shared across request-handling goroutines (a common pattern for caches,
  connection pools, or shared config) -- confirm whether every access path
  goes through a lock.
- If already in production and the race detector wasn't running, consider
  temporarily deploying a race-detector-instrumented build (`go build -race`)
  to a canary/staging instance under realistic concurrent load -- it has
  real overhead (CPU/memory), so this is a targeted diagnostic step, not a
  permanent production build.

## Fix
Identify exactly which shared state is being accessed unsynchronized, and
apply the narrowest synchronization that covers the actual access pattern:
- For simple shared counters/flags, use `sync/atomic` types (`atomic.Int64`,
  `atomic.Bool`, etc.) rather than a mutex, when the operation is a single
  value read/write/increment.
- For shared maps or multi-field structs accessed by multiple goroutines,
  guard access with a `sync.RWMutex` (`RLock` for reads, `Lock` for writes)
  so concurrent reads aren't unnecessarily serialized while writes are still
  safe.
- For lazy one-time initialization, use `sync.Once` instead of a manual nil
  check:
```go
var (
    cacheOnce sync.Once
    cache     *Cache
)
func getCache() *Cache {
    cacheOnce.Do(func() { cache = buildCache() })
    return cache
}
```
- Where feasible, prefer eliminating the shared mutable state altogether
  (construct per-request state instead of sharing a mutable singleton) over
  adding synchronization to a design that doesn't need to share state in the
  first place -- less shared state means fewer opportunities for this class
  of bug to reappear elsewhere in the same struct later.

## Pitfalls
- Adding a mutex around only the specific lines that crashed, while leaving
  other access paths to the same shared state unsynchronized, fixes the
  reported crash but leaves the underlying race present elsewhere in the
  same data -- audit *every* access path to the shared state identified, not
  just the one in the stack trace.
- Running the race detector briefly under low load and declaring victory --
  race windows can be narrow; a short or lightly-concurrent verification run
  can pass even with the bug still present, so verification needs
  concurrency and duration proportional to what surfaced it originally.
- Using `-race` builds permanently in production for peace of mind is not a
  substitute for fixing the race -- it has meaningful runtime overhead and
  is meant as a diagnostic tool, not a production safety net.

## Verify
Write (or extend) a test that drives the specific code path with a
realistic or higher-than-production goroutine count against the shared
state, run it under `go test -race -count=20` (or more), and confirm both
zero race detector reports and correct final state (e.g. a counter matching
the exact expected total) across all runs, not just an absence of a crash.
