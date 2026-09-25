---
name: defer-in-loop-resource-accumulation
description: Fix a function that runs out of file descriptors or holds locks far longer than intended because a defer statement inside a loop body doesn't run until the whole function returns.
triggers: ["too many open files", "file descriptor leak in loop", "defer inside for loop", "mutex held too long", "resource exhaustion processing batch"]
permissions: ["READ"]
---

## Symptom
A function that processes many items in a loop -- opening a file per item,
acquiring a lock per item, opening a DB connection/cursor per item -- fails
partway through a large batch with something like "too many open files"
(`EMFILE`), or holds a mutex/lock for the entire duration of the loop instead
of releasing it between iterations, causing unrelated goroutines to stall far
longer than expected. It often only shows up once input size crosses some
threshold (whatever the OS file descriptor limit or the practical contention
threshold is), so it passes small tests fine.

## Likely causes
1. **`defer f.Close()` (or `defer mu.Unlock()`, `defer rows.Close()`) placed
   directly inside a `for` loop body** -- `defer` always runs at the
   enclosing *function's* return, not at the end of the current loop
   iteration or block, so every iteration's resource stays open until the
   whole loop (and rest of the function) finishes.
2. **A helper function that itself uses `defer` correctly is not extracted**
   -- the resource-acquiring code is inlined into the loop instead of being
   its own function call, so there's no natural function boundary for the
   `defer` to bind to per-iteration.
3. **A loop over query results where each row's associated resource (a
   nested query, a streamed response body) is deferred instead of closed
   explicitly**, compounding with the outer loop's own iteration count.
4. **Mistaken belief that `defer` inside a block (e.g. an `if` or `for` body)
   is scoped to that block** -- true in some other languages' `finally` or
   `using`/`with` constructs, but Go's `defer` is always function-scoped,
   which is a frequent source of confusion for developers new to Go.

## Diagnose
- Grep the function for `defer` statements that are textually inside a `for`
  loop's braces -- any `defer` there is suspect by default; the question is
  whether the loop is bounded small enough that it doesn't matter (rare) or
  whether it can run over a large/unbounded input (the actual bug).
- Reproduce with a batch size large enough to exceed the OS's default file
  descriptor limit (`ulimit -n`, commonly 1024) and confirm the exact error
  and where it fails -- `EMFILE`/`too many open files` pinpoints file handles;
  a hang or high contention pinpoints a lock held too long.
- Use `lsof -p <pid>` (or `/proc/<pid>/fd` on Linux) while the batch is
  running to watch the open file descriptor count climb linearly with loop
  iterations instead of staying flat.
- For the mutex variant, check goroutine dumps (`SIGQUIT` or pprof) for other
  goroutines blocked on `Lock()` for the same mutex while the loop is still
  mid-run, confirming the lock is held across iterations rather than
  per-iteration.

## Fix
Extract the per-iteration body into its own function (a named helper or an
inline closure called immediately), so `defer` binds to that smaller
function's return instead of the outer loop's:
```go
for _, path := range paths {
    if err := processOne(path); err != nil {
        return err
    }
}

func processOne(path string) error {
    f, err := os.Open(path)
    if err != nil { return err }
    defer f.Close() // runs at the end of THIS call, not the whole loop
    return handle(f)
}
```
If extracting a function is awkward, an immediately-invoked closure works
identically: `func() { f, _ := os.Open(path); defer f.Close(); ... }()`. For
locks specifically, prefer acquiring and releasing explicitly around just the
critical section inside the loop (`mu.Lock(); ...; mu.Unlock()`) rather than
`defer` at all when the critical section is a small part of a larger
iteration, since explicit unlock makes the exact release point visible at a
glance.

## Pitfalls
- Wrapping the whole loop body in a closure but forgetting to check/return
  its error still leaks the *error handling*, even though the resource leak
  is fixed -- make sure the closure's return value is captured and acted on.
- Over-correcting by removing `defer` everywhere "to be safe" loses its real
  benefit (guaranteed cleanup on early return/panic) in ordinary
  non-loop functions -- the fix is scoping `defer` to a smaller function
  boundary, not avoiding `defer` in general.
- In the mutex variant, explicit `Unlock()` calls must be reached on every
  exit path including errors -- a naked `mu.Unlock()` before a `return err`
  that's later refactored to add another return path is easy to miss;
  consider keeping `defer mu.Unlock()` but inside a small extracted
  function scoped to just that critical section, combining both fixes.

## Verify
Run the batch operation with an input size at least 2-3x the platform's
default file descriptor limit (or a lock-contention benchmark with concurrent
readers) before and after the fix, and confirm open file descriptor count
(via `lsof`/`/proc/<pid>/fd`) stays roughly constant across the run instead of
growing linearly with items processed.
