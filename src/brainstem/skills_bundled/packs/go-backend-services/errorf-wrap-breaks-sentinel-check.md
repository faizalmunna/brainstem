---
name: errorf-wrap-breaks-sentinel-check
description: Fix an errors.Is or errors.As check against a known sentinel or typed error that always returns false because the error was wrapped with the wrong fmt.Errorf verb or a custom Error method.
triggers: ["errors.Is always false", "errors.As not matching", "sentinel error check fails after wrapping", "fmt.Errorf breaks error comparison", "custom error type not detected by errors.As"]
permissions: ["READ"]
---

## Symptom
Code that checks `errors.Is(err, sql.ErrNoRows)` (or any other sentinel), or
`errors.As(err, &myErrType)` for a custom error type, returns `false` even
though the underlying error genuinely is that sentinel/type somewhere in the
call chain -- so error-specific handling (return 404 instead of 500, retry
only on a specific error, etc.) never triggers, and the error falls through
to a generic handler instead.

## Likely causes
1. **The error was wrapped with `fmt.Errorf("...: %v", err)` instead of
   `%w`** -- `%v` formats the error's message into a new string but discards
   the original error value entirely, so there is no chain left for
   `errors.Is`/`errors.As` to walk; the new error is a completely unrelated
   value from the sentinel's perspective.
2. **A custom error type implements `Error() string` but not `Unwrap() error`**
   when it wraps an inner error in a struct field -- without `Unwrap`,
   `errors.Is`/`errors.As` has no way to traverse into that field, even
   though the inner error is right there in the struct.
3. **The error passes through a boundary that discards it entirely and
   constructs a new one** -- e.g. an HTTP client mapping any non-2xx response
   to a generic `errors.New("request failed")`, or a gRPC status conversion
   that loses the original Go error -- so there is genuinely nothing left to
   unwrap to, not just a wrapping mistake.
3.1. **Comparing with `==` against a sentinel after wrapping**, instead of
   using `errors.Is` at all -- direct equality never matches a wrapped error
   even when wrapped correctly with `%w`, since the wrapped value is a
   different concrete error value.
4. **Multiple layers of wrapping where one intermediate layer uses `%v`**,
   breaking the chain partway through even though the layers above and below
   that one wrap correctly -- the chain is only as good as its weakest link.

## Diagnose
- Grep the call path between where the sentinel/typed error originates and
  where the `errors.Is`/`errors.As` check happens, for every `fmt.Errorf`
  call -- check each one's verb (`%w` vs `%v`) for the error argument.
- For a custom error struct, check whether it defines
  `func (e *MyError) Unwrap() error` returning the wrapped field -- if it only
  defines `Error() string`, that's the gap.
- Write a small standalone test that constructs the error through the exact
  same call chain as production and asserts `errors.Is(err, sentinel)` (or
  `errors.As`) directly -- this isolates the break to a specific layer faster
  than reasoning about the whole chain at once.
- Use `%+v` or a debugger to print the concrete type of `err` at the
  point of the failing check -- if it's a plain `*errors.errorString` (what
  `errors.New`/`fmt.Errorf` without `%w` produce as a flat, unwrappable
  value) instead of a wrapping type, that confirms the chain was severed
  upstream.

## Fix
Wrap with `%w`, always, whenever the intent is "this error occurred while
doing X, but callers may still want to know what specifically went wrong":
```go
row := db.QueryRow(...)
if err := row.Scan(&v); err != nil {
    return fmt.Errorf("scanning user row: %w", err) // preserves err in the chain
}
```
For custom error types wrapping another error, implement `Unwrap`:
```go
type QueryError struct {
    Query string
    Err   error
}
func (e *QueryError) Error() string { return fmt.Sprintf("query %q: %v", e.Query, e.Err) }
func (e *QueryError) Unwrap() error { return e.Err }
```
This makes `errors.Is(err, sql.ErrNoRows)` and `errors.As(err, &queryErr)`
both work regardless of how many `QueryError`/`%w` layers sit in between,
since both walk the `Unwrap` chain automatically. At any boundary where the
original error genuinely cannot or should not cross (e.g. don't leak internal
DB errors across a public API), make that an explicit, documented decision --
map to a defined sentinel/type at that boundary rather than accidentally
discarding it via `%v`.

## Pitfalls
- Wrapping *everything* with `%w` indiscriminately can leak internal
  implementation details (a raw driver error, a filesystem path) across
  abstraction boundaries where callers shouldn't be checking `errors.Is`
  against internal sentinels at all -- decide deliberately which boundaries
  preserve the chain and which intentionally translate to a new, boundary-
  appropriate error.
- `errors.As` requires the second argument to be a pointer to a type that
  implements `error` (e.g. `var pathErr *fs.PathError; errors.As(err,
  &pathErr)`) -- passing a non-pointer or the wrong concrete type compiles in
  some cases but never matches; double check the target type matches exactly
  what's constructed upstream.
- Multiple `%w` verbs in a single `fmt.Errorf` call (wrapping two errors at
  once, supported since Go 1.20) changes `Unwrap` to return `[]error` instead
  of `error` -- code written against the older single-`Unwrap() error`
  assumption needs updating if this pattern is introduced.

## Verify
Add a table-driven test that constructs the error through the real call chain
(not a synthetic shortcut) and asserts `errors.Is(err, sentinel)` returns
`true` (or `errors.As(err, &target)` returns `true` and populates `target`
correctly) for every layer currently in the chain, so a future refactor that
reintroduces a `%v` breaks a test instead of silently regressing.
