---
name: interface-satisfaction-silently-broken-by-signature-change
description: Track down a runtime failure or unexpected fallback behavior caused by a type silently no longer satisfying an interface after a method signature changed.
triggers: ["type used to implement interface but now doesn't", "interface assertion fails after refactor", "mock silently stopped matching interface", "method rename broke interface implementation quietly", "ok is false after type assertion unexpectedly"]
permissions: ["READ"]
---

## Symptom
Code that relies on a type implementing an interface -- often checked via a
type assertion with the two-value form (`v, ok := x.(SomeInterface)`), or
passed to a function accepting the interface type -- starts silently taking
the "doesn't implement it" branch, or a previously-working call chain now
fails at runtime, after a seemingly unrelated refactor: a method was
renamed, its parameter types changed, or its receiver was changed from a
value to a pointer (or vice versa) on the interface's declared type but not
on the implementing type, or the reverse. Because Go's interface
satisfaction is fully structural and implicit, there is no compiler link
between the interface definition and its implementations to force a matching
update -- if the assertion path used `ok` rather than a hard `.(T)` type
assertion, this fails silently at runtime instead of at compile time.

## Likely causes
1. **A method on the concrete type was renamed, or had a parameter/return
   type changed, without updating (or noticing) that it was implementing an
   interface elsewhere in the codebase** -- because Go never requires a type
   to declare "I implement interface X," there's no compiler error pointing
   back to the interface; the type simply stops satisfying it, and nothing
   says so unless something explicitly asserts or converts to that
   interface type.
2. **The interface itself was widened (a method added) as part of a
   refactor, and one implementation among several was missed** -- common
   when an interface has many implementers (production types plus test
   mocks/fakes), and only the production types were updated while a
   hand-written test double was not, so tests using the double silently stop
   compiling only where the double is directly used as that interface type,
   and pass wherever a two-value assertion just evaluates to `ok == false`
   and falls back to different (untested) behavior instead of failing loudly.
3. **A receiver type changed from value to pointer (or vice versa) on some
   but not all methods needed for the interface**, changing which form (`T`
   vs `*T`) has the full method set required -- code passing the "old" form
   (that used to satisfy the interface) now doesn't, and if that pass-through
   happens via an `interface{}`/`any` value with a checked assertion, it
   fails quietly rather than at the call site.
4. **No compile-time assertion exists anywhere in the codebase confirming
   the type implements the interface**, so there's nothing to fail loudly
   and immediately at the point of the breaking change -- the failure only
   surfaces later, at whatever runtime code path actually exercises the
   interface conversion, which may be far from the method that changed and
   may only be exercised by a rarely-hit code path or test.

## Diagnose
- When a two-value type assertion (`v, ok := x.(Interface)`) is behaving
  unexpectedly, first check `ok` directly in a debugger or temporary log --
  confirming `ok == false` narrows the problem to "type no longer satisfies
  interface" versus some other logic bug.
- Try a direct, non-comma-ok conversion (`var _ Interface = concreteValue`)
  in a throwaway `_test.go` file or scratch file -- the compiler will name
  the exact missing or mismatched method, which is far faster than manually
  diffing method sets by eye.
- `git log -p` / `git blame` on both the interface definition and the
  concrete type's method set to find the specific commit that changed a
  method signature, name, or receiver type -- interface satisfaction breaks
  are almost always traceable to one specific, identifiable diff even though
  the symptom appears elsewhere.
- Search the whole module for other types intended to implement the same
  interface (other production implementations, and especially hand-written
  test mocks/fakes in `_test.go` files) and check each one's method set
  against the current interface definition -- a widened interface often
  breaks exactly one overlooked implementer among several.

## Fix
Add a compile-time interface satisfaction assertion next to every type meant
to implement a given interface, so any future signature drift fails the
build immediately at the type definition, not later at a runtime call site:
```go
type FileStore struct{ /* ... */ }
func (f *FileStore) Get(key string) ([]byte, error) { /* ... */ }
func (f *FileStore) Put(key string, data []byte) error { /* ... */ }

// compile-time check: breaks the build the moment FileStore stops matching Store
var _ Store = (*FileStore)(nil)
```
Place the same assertion next to hand-written test doubles/mocks, not just
production types -- this is exactly the case most likely to be missed when
an interface changes, since test doubles are edited less often than
production code and a broken one may not be exercised until CI runs the
specific test that uses it.

## Pitfalls
- Relying on a mocking framework that generates mocks from the interface
  definition (e.g. `mockgen`) without regenerating after every interface
  change silently reintroduces this exact problem one level removed --
  regenerating mocks needs to be part of the same change, ideally enforced
  by a `go generate` check in CI, not a manual reminder.
- Adding the `var _ Interface = (*T)(nil)` assertion only for the "main"
  production implementation and not for less-obvious implementers (adapters,
  decorators, wrapper types embedding the real implementation) leaves the
  same blind spot for exactly the types most likely to drift unnoticed.
- Treating a two-value type assertion's `ok == false` branch as an
  acceptable permanent fallback path rather than investigating why it's
  false -- sometimes the comma-ok form is used defensively for a genuinely
  optional interface (fine), but when it's guarding a conversion that was
  always expected to succeed, silently falling back masks the actual
  regression instead of surfacing it.

## Verify
After adding compile-time assertions for every intended implementer,
run `go build ./...` and `go vet ./...` across the whole module -- confirm
it fails loudly (naming the exact missing method) if you temporarily
reintroduce the breaking signature change in a scratch branch, proving the
assertion actually catches this class of regression before it reaches a
runtime code path or CI test run.
