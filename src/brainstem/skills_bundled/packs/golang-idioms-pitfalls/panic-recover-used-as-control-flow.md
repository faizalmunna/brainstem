---
name: panic-recover-used-as-control-flow
description: Refactor code that uses panic and recover for ordinary error signaling instead of Go's idiomatic explicit multi-value error returns.
triggers: ["panic used for normal error handling", "recover swallowing errors silently", "why does this function panic instead of returning error", "overuse of panic in business logic", "recover hiding bugs in production"]
permissions: ["READ"]
---

## Symptom
Business logic that isn't a genuinely unrecoverable programmer error (bad
input validation, "record not found," a failed downstream call) is signaled
by calling `panic(...)`, and a `recover()` somewhere up the call stack
converts it back into a value or an error -- effectively reimplementing
exceptions on top of Go's panic mechanism. Symptoms include: stack traces in
logs for routine, expected conditions; a `recover()` in the middle of
business logic (not just at a goroutine boundary or top-level server
handler) that silently swallows the panic and returns a generic error,
discarding the real cause; or difficulty writing unit tests for specific
error conditions because the only way to trigger them is via a panicking
code path deep in a call chain.

## Likely causes
1. **A deeply nested call chain wants to "bail out early" from many levels
   at once without threading an `error` return value through every
   intermediate function**, and `panic`/`recover` is used as a shortcut
   long-jump mechanism instead of returning errors up the stack normally --
   this trades a small amount of boilerplate for much harder-to-follow
   control flow and loses caller-level context about exactly what failed.
2. **Someone ported logic from an exception-based language (Java, Python,
   JS/TS)** where `throw`/`try`/`catch` is the idiomatic error-handling
   mechanism, and translated `throw` directly to `panic` and `catch` to
   `recover` without adapting to Go's convention of explicit `(result,
   error)` returns for expected failure conditions.
3. **A parsing/validation library panics on malformed input "because it's
   simpler to write recursively without threading errors,"** and the top-level
   caller wraps every call in a `recover()`-based helper -- this works but
   means every consumer of the library must remember to wrap calls, and any
   consumer who forgets crashes the whole process instead of getting a
   normal error value.
4. **A `recover()` is placed too broadly (e.g. wrapping an entire request
   handler or an entire package's worth of logic in one deferred recover)**,
   so it silently catches and converts *any* panic in that scope --
   including genuine programmer bugs like nil dereferences or out-of-bounds
   indexing -- into a generic "something went wrong" error, hiding real
   defects that should have crashed loudly and been fixed, not swallowed.

## Diagnose
- Grep the codebase for `panic(` calls outside of `main`, `init`, and
  genuinely unrecoverable invariant violations, and classify each: is the
  condition being panicked on something a caller could reasonably expect and
  handle (bad input, missing record, a failed external call)? If yes, it's a
  candidate for this antipattern.
- For each `recover()` call, check its scope -- is it immediately around a
  single well-understood panicking call, or does it wrap a large block/entire
  handler? A broad recover is a stronger signal of "using recover as generic
  exception handling" than a narrow one guarding a specific known-panicky
  dependency call.
- Check whether `recover()`'s result is inspected and distinguished by type/
  content, or discarded into a generic `errors.New("internal error")` --
  discarding it is direct evidence real error information is being lost
  through this pattern.
- Search test files for tests that must trigger a panic (`assert.Panics` /
  `recover()` inside the test itself) to exercise an expected-failure code
  path -- needing to test via panic for something that isn't an invariant
  violation is a strong tell that it should be a normal error return instead.

## Fix
Convert routine, expected failure conditions to standard Go error returns,
reserving `panic` for genuine programmer errors/invariant violations that
indicate a bug (and are not expected to be handled by a caller at all):
```go
// before: panic used for an expected, handleable condition
func GetUser(id string) *User {
    u, ok := store[id]
    if !ok {
        panic(fmt.Sprintf("user %s not found", id))
    }
    return u
}
// after: idiomatic explicit error return
func GetUser(id string) (*User, error) {
    u, ok := store[id]
    if !ok {
        return nil, fmt.Errorf("user %s not found: %w", id, ErrNotFound)
    }
    return u, nil
}
```
Reserve `recover()` for two narrow, legitimate uses: (1) at a goroutine's
top level, to prevent one goroutine's panic from crashing the whole process
and instead log/report it (common in a server's per-request goroutine); and
(2) at a package's public API boundary specifically converting a *documented*
internal panic (e.g. in a recursive parser that panics internally for
implementation simplicity) back into an error for external callers, with the
recovered value inspected and re-panicked if it isn't the expected sentinel
type.

## Pitfalls
- Recovering a panic and returning a generic wrapped error without
  re-panicking on unexpected panic values (like a nil-pointer dereference
  that has nothing to do with the intended control-flow panic) hides real
  bugs -- a recover handler should check the recovered value's type/content
  and re-panic anything that isn't the specific expected sentinel.
- Removing `panic`/`recover` everywhere including the legitimate goroutine-
  top-level "don't crash the whole process" use case throws away a genuinely
  idiomatic safety net -- the fix targets panic used *for business logic
  control flow*, not the narrower, accepted crash-isolation use.
- Converting panics to errors but leaving call sites that still need to
  propagate the error up several layers without adding `if err != nil` checks
  at each level -- the whole point of the refactor is making failure paths
  explicit and visible, so skipping error checks at intermediate layers
  reintroduces the same "invisible control flow" problem in a different form.

## Verify
Grep for `panic(` in the affected package after the refactor and confirm
each remaining call is either in `main`/`init`, guards a true invariant
(commented as such), or is inside a narrowly-scoped, documented internal
implementation detail with a matching `recover()` at the package's public
boundary. Add a unit test for the previously-panicking condition that now
calls the function directly and asserts on the returned `error` value (using
`errors.Is`/`errors.As` as appropriate) without needing `recover()` anywhere
in the test itself.
