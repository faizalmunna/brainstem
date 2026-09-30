---
name: defer-arguments-evaluated-eagerly
description: Fix a deferred function call that logs or uses a stale value because its arguments were evaluated immediately at the defer statement, not when it actually runs.
triggers: ["defer logged wrong value", "deferred function used stale variable", "defer argument evaluated too early", "elapsed time always zero with defer", "defer captured value at wrong time"]
permissions: ["READ"]
---

## Symptom
A `defer` statement that's meant to log or use a value "as of when the
function returns" instead consistently shows the value from "as of when the
`defer` statement itself ran" -- e.g. `defer log.Println("result:", result)`
placed near the top of a function always prints the zero value of `result`
even though `result` is clearly set to something else before the function
returns; or `defer fmt.Println("elapsed:", time.Since(start))` prints an
elapsed time of essentially zero because `time.Since(start)` was computed
immediately at the `defer` line, not at actual function exit.

## Likely causes
1. **Misunderstanding of `defer`'s evaluation timing: the deferred
   function's arguments are evaluated immediately, at the point the `defer`
   statement executes, while only the *call* itself is postponed** --
   `defer log.Println("result:", result)` evaluates `result` right then
   (capturing whatever it is at that line), and only the actual `Println`
   invocation is delayed until function exit.
2. **`defer someFunc(time.Now())` or similar pattern intended to measure
   elapsed time, but the duration calculation itself is placed outside the
   deferred call** -- e.g. `defer fmt.Println(time.Since(start))` computes
   `time.Since(start)` eagerly (a near-zero duration at the defer line)
   instead of at actual exit; the fix requires wrapping the *computation*,
   not just the printing, in the deferred closure.
3. **A named return value is intended to be modified by a deferred function
   for logging or error-wrapping purposes**, but the deferred call
   references a local variable copy taken before the return statement
   executes, rather than referencing the named return variable itself by
   closure -- so a deferred "log the final error" call prints `nil` even
   though the function actually returned a non-nil error.
4. **Copy-pasted logging/tracing boilerplate from one function to another**
   where the original used a closure form correctly but the copy was
   simplified to a direct call with arguments, silently reintroducing eager
   evaluation.

## Diagnose
- Read the exact deferred statement's argument list -- if any argument is a
  variable (not a literal) or an expression like `time.Since(x)`, ask "is
  this evaluated now or later?" The rule is unconditional: arguments are
  always evaluated at the `defer` statement's execution, only the function
  call is deferred.
- Add a temporary print immediately before the `defer` line and another
  inside what the defer actually logs, comparing timestamps/values -- if the
  "before defer" value matches what gets logged (rather than the value right
  before the function returns), that confirms eager argument evaluation is
  the cause.
- For the named-return-value variant specifically, check whether the
  function declares named returns (`func f() (result int, err error)`) and
  whether the deferred function is a closure with no parameters that
  references `result`/`err` directly (correct -- reads the latest value at
  exit) versus a function called with `result`/`err` passed as arguments
  (incorrect -- captures the value at defer time).
- `go vet` does not catch this by default; rely on manual review of every
  `defer` statement whose arguments aren't literals, particularly around
  timing/logging/error-wrapping code.

## Fix
Wrap the value-dependent logic in a closure with no arguments so the
variable is read at actual execution time (function exit), not at the
`defer` statement's evaluation time:
```go
// before: result and time.Since(start) both evaluated immediately
defer log.Println("result:", result)
defer fmt.Println("elapsed:", time.Since(start))

// after: closures defer the *read*, not just the call
defer func() { log.Println("result:", result) }()
defer func() { fmt.Println("elapsed:", time.Since(start)) }()
```
For named return values that a deferred function should observe or modify
(a common pattern for wrapping the final error with context), use a
no-argument closure that references the named returns directly by name:
```go
func doWork() (n int, err error) {
    defer func() {
        if err != nil {
            err = fmt.Errorf("doWork: %w", err) // sees and can modify final err
        }
    }()
    // ...
    return computeN(), maybeFail()
}
```

## Pitfalls
- Wrapping *everything* in a closure out of caution, including cases where
  eager evaluation is actually correct and intended (e.g. deliberately
  capturing a resource handle's value at defer time to release that specific
  handle, like `defer f.Close()` where `f` itself doesn't change) --
  understand which semantic is wanted before reflexively adding a closure.
- Using a closure to read a named return value but declaring the function's
  returns as unnamed and trying to reference a local variable instead --
  without named returns, there is no way for a deferred closure to observe
  or modify what the function actually returns, only the local variable's
  last-assigned value before the `return` statement executed it into the
  (separate) return slot.
- Forgetting the trailing `()` that actually invokes the closure (`defer
  func() { ... }` without calling it) is a compile error, but forgetting
  it on a variadic helper wrapped incorrectly can silently defer the wrong
  thing -- double check the deferred expression is a call, not just a
  function value, when refactoring an existing defer into closure form.

## Verify
Add a table or scenario test that sets the relevant variable (or waits a
measurable amount of real or mocked time) *after* the `defer` statement
executes but *before* the function returns, then asserts the logged/returned
value reflects the post-defer-statement state -- for the timing case
specifically, assert `elapsed` is at least as large as a known injected
delay, which would fail under the eager-evaluation bug (near-zero duration)
and pass once wrapped in a closure.
