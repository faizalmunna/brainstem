---
name: waitgroup-negative-counter-panic
description: Fix a sync.WaitGroup panic reporting a negative WaitGroup counter that occurs intermittently under real concurrency but not in every run.
triggers: ["sync: negative waitgroup counter", "waitgroup panic under load", "wg.Done called too many times", "waitgroup counter goes negative intermittently", "panic negative WaitGroup counter"]
permissions: ["READ"]
---

## Symptom
The process panics with `panic: sync: negative WaitGroup counter`, and it
happens inconsistently -- passing most runs, failing occasionally, more often
under real production concurrency or load testing than in a quick local run
or a single-threaded test. Because it's intermittent, it's easy to dismiss as
a flaky test rather than a real correctness bug.

## Likely causes
1. **`Add` and `Done` counts don't actually match on every code path** -- a
   goroutine is spawned with `wg.Add(1)` on the assumption it will call
   `wg.Done()` exactly once, but an early-return branch (an error, a panic
   recovered elsewhere, a short-circuit) skips the `defer wg.Done()` because
   it was placed after the branch instead of immediately after `Add`.
2. **`wg.Add(1)` is called inside the spawned goroutine instead of before
   `go func(){...}()`** -- if the goroutine hasn't been scheduled yet by the
   time `wg.Wait()` runs (a real race, not guaranteed either way), `Wait` can
   return before that `Add` ever executes, and the accounting for how many
   `Done` calls are "expected" no longer matches how many goroutines actually
   ran.
3. **The same `wg.Done()` runs more than once for a single unit of work** --
   e.g. both a deferred `wg.Done()` and an explicit one on a specific
   branch, or a retry loop that re-enters a function whose `defer wg.Done()`
   fires on every retry attempt instead of once per originally-added unit.
4. **A shared `WaitGroup` is reused across batches without full separation**
   -- a new batch calls `Add` again while a previous batch's goroutines are
   still finishing and calling `Done` for the old batch, so the counts get
   attributed to the wrong batch and the arithmetic no longer lines up.

## Diagnose
- Read the exact panic message and stack trace -- it identifies which
  `Done()` call site drove the counter negative, which narrows the search to
  that call site's surrounding function.
- Audit every path out of the goroutine body for that call site: does
  *every* return path (success, each error branch, a recovered panic) reach
  exactly one `Done()` call? A `defer wg.Done()` placed as the very first
  line after entering the goroutine covers all paths; anything placed later
  or conditionally does not.
- Confirm `wg.Add(n)` happens before `go func(){}()` is invoked, in the
  same goroutine that will call `Wait()` -- not inside the spawned goroutine
  itself.
- Run the suspect code repeatedly under `go test -race -count=100` (or
  higher) -- the race detector won't flag the counter mismatch directly, but
  running many iterations under load surfaces the intermittent failure
  reliably enough to bisect which code path triggers it.
- Check for WaitGroup reuse across logical batches -- grep for the same
  `sync.WaitGroup` variable being used in more than one loop/batch without a
  fresh instance or a guaranteed full `Wait()` between batches.

## Fix
Call `Add` immediately before spawning, and pair it with a single
unconditional `defer wg.Done()` as the very first statement inside the
goroutine, so it's structurally impossible for a code path to skip it:
```go
for _, item := range items {
    wg.Add(1)
    go func(item Item) {
        defer wg.Done() // always runs, regardless of how this goroutine exits
        process(item)   // any error/panic inside doesn't skip Done
    }(item)
}
wg.Wait()
```
If work is added dynamically from multiple goroutines (not a simple upfront
loop), make sure every `Add` call happens-before the corresponding `Wait`
could observe it -- generally by only ever calling `Add` from the same
goroutine that will call `Wait`, never from a goroutine that might itself
race with `Wait` starting. For per-batch reuse, construct a new
`sync.WaitGroup` per batch instead of resetting/reusing one, since a fresh
zero-value WaitGroup can't carry over stale accounting from a previous batch.

## Pitfalls
- Recovering from a panic inside the goroutine but placing that recovery
  *after* the point where `wg.Done()` should have run means a panicking
  unit of work never signals completion at all, hanging `Wait()` forever
  instead of panicking with a negative counter -- put `defer wg.Done()`
  before `defer func(){ recover() }()` executes conceptually, i.e. as the
  very first defer registered, since defers run in LIFO order and both need
  to fire.
- Calling `wg.Add()` with a variable count computed from a slice that a
  concurrent goroutine might still be appending to can produce a count that
  doesn't match the actual number of goroutines spawned -- compute the count
  from a snapshot, not a live, mutating collection.
- Sharing one `WaitGroup` across unrelated concurrent operations "to save an
  allocation" makes failures in one operation corrupt the counter for a
  completely unrelated one -- scope a WaitGroup to exactly one batch of
  related work.

## Verify
Run the code path under `go test -race -count=200` (or a load test driving
enough concurrent batches to previously trigger the panic within a handful of
runs) and confirm zero panics across all runs, plus add an explicit test that
forces one goroutine down each error/early-return branch and asserts
`wg.Wait()` returns without panicking or hanging for each one individually.
