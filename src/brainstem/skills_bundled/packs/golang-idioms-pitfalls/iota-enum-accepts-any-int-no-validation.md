---
name: iota-enum-accepts-any-int-no-validation
description: Fix bugs from a Go iota-based enum silently accepting out-of-range integer values and printing unreadable numbers instead of names.
triggers: ["enum prints as a number not a name", "invalid enum value not caught at compile time", "iota constant accepts any integer", "switch on enum missing default silently no-ops", "unknown status code passed no error"]
permissions: ["READ"]
---

## Symptom
A type built from `iota`-based constants (a common Go stand-in for an enum,
since Go has no native enum type) shows one of two failure patterns: (1) a
value of that type gets logged, serialized, or displayed and shows up as a
bare, meaningless integer (`Status: 3`) instead of a readable name, because
no `String()` method was implemented; or (2) a completely out-of-range value
-- like `Status(99)` where only 0-3 are defined -- is accepted anywhere the
named type is expected, compiles fine, and flows through the system (stored
in a DB, passed to a `switch`) without any error, because the underlying
type is just an `int` and Go performs no range validation on named integer
types at compile time or by default at runtime.

## Likely causes
1. **The enum type has no `String() (fmt.Stringer)` method defined**, so
   every place it's formatted with `%v`/`%s`, logged, or included in an error
   message falls back to printing the bare underlying integer -- this is
   easy to miss because the code compiles and runs correctly, it's just
   unreadable in logs, debugger output, and error messages.
2. **A value is constructed via an explicit conversion from an arbitrary
   integer (`Status(userInput)`) rather than only ever being assigned one of
   the declared named constants**, and nothing validates the result is one
   of the defined values -- common at deserialization boundaries (parsing a
   query param, reading a DB column, unmarshaling JSON) where the raw
   integer comes from outside the program's control.
3. **A `switch` statement over the enum's values has no `default` case**,
   so when an unexpected/invalid value does reach it (from cause 2, or from
   a later addition of a new enum value that this particular switch wasn't
   updated for), the switch silently falls through and does nothing instead
   of surfacing that an unhandled case was hit.
4. **The enum's zero value (`iota` starting at 0) is given the same
   underlying value as a meaningful defined constant**, rather than being
   reserved as an explicit "unset/unknown" sentinel -- so a struct field
   left unset (Go's normal zero-value default) is silently indistinguishable
   from a deliberately-chosen first enum value.

## Diagnose
- Grep the type definition for a `func (s Status) String() string` (or
  equivalent) -- its absence directly explains bare-integer output anywhere
  the value is formatted or logged.
- Grep for explicit conversions to the enum type from a non-constant source
  (`Status(` followed by a variable, not one of the named constants) --
  each one is a point where an invalid value could enter without validation;
  cross-check whether a validating helper (an `IsValid()` method or a
  parsing function that checks range/membership) is called right after.
- Grep every `switch` statement over the enum type for a missing `default`
  case -- specifically check what happens on that missing branch: does the
  surrounding code silently continue with no action, or is there external
  handling (an error return) that makes the omission safe?
- Check whether `iota` starts at 0 for a semantically meaningful first value,
  or whether the enum deliberately reserves 0 as `StatusUnknown`/
  `StatusUnspecified` -- grep struct definitions for fields of this enum type
  and confirm whether "never explicitly set" (zero value) is distinguishable
  from "explicitly set to the first defined constant."

## Fix
Give every `iota`-based enum a `String()` method (often via `go generate` and
`stringer`, or hand-written for small enums) so it's always readable in logs
and `%v` output, and add an explicit validity check used at every boundary
where an untrusted integer is converted into the enum type:
```go
type Status int
const (
    StatusUnknown Status = iota // reserve zero as an explicit "unset" sentinel
    StatusPending
    StatusActive
    StatusClosed
)
func (s Status) String() string {
    switch s {
    case StatusPending: return "pending"
    case StatusActive:  return "active"
    case StatusClosed:  return "closed"
    default:            return fmt.Sprintf("Status(%d)", int(s)) // unknown, but visible
    }
}
func (s Status) Valid() bool {
    return s >= StatusPending && s <= StatusClosed // StatusUnknown intentionally excluded
}
func ParseStatus(raw int) (Status, error) {
    s := Status(raw)
    if !s.Valid() {
        return StatusUnknown, fmt.Errorf("invalid status value %d", raw)
    }
    return s, nil
}
```
Add a `default` case to every `switch` over the enum that returns an error
or logs loudly on an unhandled value, rather than silently doing nothing --
this also makes the compiler-invisible cost of adding a new enum constant
later (every switch needs updating) visible at runtime instead of silently
mishandled.

## Pitfalls
- Using `stringer`-generated `String()` methods but forgetting to re-run
  `go generate` after adding a new constant leaves the generated method
  silently out of sync (new value prints as a raw number, or the generated
  code panics/indexes out of bounds depending on the generator) -- wire
  `go generate ./...` into CI or a pre-commit check for any package using it.
- Adding a `default` case to a switch that just logs and continues can mask
  the same problem it's meant to catch if the log line is easy to miss in
  practice (buried in noisy output) -- for anything security- or billing-
  adjacent, prefer returning an explicit error over the unhandled case
  instead of only logging.
- Relying on `Valid()` at the deserialization boundary but constructing the
  enum via direct conversion elsewhere in the same codebase (bypassing
  `ParseStatus`) reintroduces the exact gap the boundary check was meant to
  close -- grep for other direct `Status(` conversions once the validating
  constructor exists, and prefer making the underlying type unexported so
  external packages are forced through the validating constructor.

## Verify
Write a table test that calls the parsing/validating constructor with every
defined constant (expect success), the reserved zero/unknown sentinel
(expect either success with `StatusUnknown` or a defined "empty" error,
whichever is the intended contract), and at least one clearly out-of-range
integer like `-1` and `9999` (expect an error, not a silently accepted
invalid `Status` value) -- and separately assert `String()` on every defined
constant returns its intended readable name, not a bare integer.
