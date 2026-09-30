---
name: for-loop-variable-capture-closure-goroutine
description: Fix closures or goroutines launched inside a for range loop that all observe the same final loop variable value instead of each iteration's own value.
triggers: ["all goroutines printed the same value", "closure captured wrong loop variable", "for range loop variable same value every time", "go func in loop uses last value", "loop variable capture bug"]
permissions: ["READ"]
---

## Symptom
A `for i, v := range items` loop starts a goroutine or stores a closure per
iteration (e.g. `go func() { fmt.Println(v) }()`, or appending
`func() { use(v) }` to a slice of callbacks), and when those goroutines or
callbacks finally run, most or all of them print/use the *same* value --
typically the last element's value, or something clearly wrong -- instead of
each iteration's own distinct value. It reproduces inconsistently under `go
run` (depends on scheduler timing) but is deterministic for stored closures
run later.

## Likely causes
1. **Building/running on Go before 1.22 (or a codebase that assumes the old
   semantics for compatibility)** -- prior to Go 1.22, the loop variable(s) in
   `for range` were a single set of variables reused and mutated across every
   iteration, not freshly declared per iteration; any closure capturing them
   by reference sees whatever the variable holds at the time the closure
   actually runs, which by then is usually the final iteration's value.
2. **The team upgraded the Go toolchain to 1.22+ but the module's `go.mod`
   `go` directive is still set below 1.22**, so the compiler keeps the old
   per-loop-not-per-iteration semantics for that module regardless of the
   installed toolchain version -- a very easy thing to miss since the code
   "should" be fixed by the new Go version but silently isn't.
3. **A closure captures the loop variable itself instead of a local copy**,
   even on Go 1.22+, in code that manually re-implements iteration with a
   `for i := 0; i < n; i++` style C-like loop instead of `for range` --
   the 1.22 per-iteration fix applies specifically to `for range` (and
   3-clause `for` loops with a range-like variable get the fix too in 1.22,
   but any hand-rolled index variable shared across manually spawned closures
   outside a loop construct entirely is not covered).
4. **Copy-pasted or AI-generated code trained on pre-1.22 idioms** still
   includes the defensive `v := v` shadow pattern or, worse, omits it
   entirely because a training example assumed new semantics that don't
   apply to the target module's Go version.

## Diagnose
- Check the exact Go version semantics in play: run `go version` for the
  toolchain, and check the `go` directive in `go.mod` -- the per-iteration
  variable fix (Go 1.22, proposal #60078) applies based on the `go.mod`
  version, not just the installed compiler.
- Reproduce deterministically without relying on goroutine timing: instead of
  `go func(){ use(v) }()`, first replace it with a non-concurrent version that
  appends `func(){ use(v) }` to a `[]func()` slice, then call each stored
  closure after the loop -- this removes scheduler nondeterminism and makes
  the "they're all the same value" bug 100% reproducible if it exists.
- Add `fmt.Printf("iteration captured addr=%p val=%v\n", &v, v)` right before
  the closure/goroutine is created -- if every iteration prints the same
  address, the variable is being reused across iterations (pre-1.22
  semantics or a manually shared variable).
- `go vet` (recent versions) and `golangci-lint`'s `loopclosure`/`scopelint`-
  style checkers flag the classic case of capturing a range variable inside a
  `go func()` or a deferred closure directly -- run it even on 1.22+ code
  bases that mix old and new Go module versions across a monorepo.

## Fix
On Go 1.22+ with `go.mod`'s `go` directive at 1.22 or later, the language fix
already gives each iteration its own variable, so `for _, v := range items {
go func() { use(v) }() }` is correct as written -- the fix here is often just
raising the `go` directive, not touching the loop body. For code that must
support pre-1.22 semantics (older `go.mod`, or defensive clarity regardless of
version), shadow the variable inside the loop body so each iteration gets its
own copy, or pass it explicitly as a parameter to the closure/goroutine:
```go
for _, v := range items {
    v := v // shadow: new variable per iteration, pre-1.22 safe
    go func() { use(v) }()
}
// equivalently, and often clearer:
for _, v := range items {
    go func(v int) { use(v) }(v) // v passed by value at call time
}
```

## Pitfalls
- Adding `v := v` shadowing everywhere as a blanket habit even on a
  `go.mod` already declaring 1.22+ is harmless but adds noise reviewers now
  have to double-check isn't hiding a *different* bug -- prefer relying on the
  language guarantee once the module genuinely targets 1.22+, and reserve the
  explicit shadow/parameter pattern for code that must stay compatible with
  older `go.mod` versions.
- Assuming raising `go.mod`'s `go` directive to 1.22 alone is a purely
  additive safety fix with no other effect -- it's a real behavior change for
  any pre-existing loop that accidentally *relied* on the old shared-variable
  behavior (e.g. intentionally reading the final value after the loop),
  which is rare but worth a one-time audit, not just a version bump.
- Fixing only the outermost loop variable in a nested `for range` and missing
  that the inner loop's variable has the exact same capture problem
  independently.

## Verify
Write a test that ranges over a slice of at least 3 distinct values, appends
a closure capturing the loop variable into a slice per iteration, then -- after
the loop completes -- calls each stored closure and asserts the observed
values match the original slice in order (not all equal to the last element).
This isolates the capture semantics from goroutine scheduling entirely.
