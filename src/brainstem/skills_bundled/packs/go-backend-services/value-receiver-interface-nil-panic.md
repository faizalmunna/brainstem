---
name: value-receiver-interface-nil-panic
description: Fix a runtime nil pointer panic or unexpected interface satisfaction caused by mixing pointer and value receivers when assigning a concrete type to an interface variable.
triggers: ["nil pointer dereference interface method", "interface holds non-nil type but nil value", "does not implement interface pointer receiver", "typed nil interface panic", "value receiver vs pointer receiver interface bug"]
permissions: ["READ"]
---

## Symptom
Two related but distinct failure modes show up under this pattern: (1) a
compile error like `MyType does not implement MyInterface (method Foo has
pointer receiver)` when a value (not a pointer) is passed where the interface
is expected, or (2) worse, code compiles fine but panics at runtime with a
nil pointer dereference inside a method call, even though a preceding `if x
!= nil` check on the interface variable passed -- because the interface
holds a typed nil pointer, which is not itself `nil` as an interface value.

## Likely causes
1. **A type's method set only includes pointer-receiver methods, but a value
   (not `&value`) is passed where the interface is expected** -- Go's method
   set rules mean a value type `T` only satisfies an interface with the
   methods defined on `T` (value receiver), not `*T` (pointer receiver)
   methods; passing a `T` value where `*T` is needed to satisfy the interface
   is a compile error, not a runtime one, but is often "fixed" by taking the
   address in a way that reintroduces problem 2.
2. **A function returns a typed nil pointer (`var p *ConcreteType; return
   p`) as an interface return type**, and the caller checks `if result !=
   nil` -- this check is true even though `p` is nil, because the interface
   value has a non-nil concrete type (`*ConcreteType`) with a nil value inside
   it; only the pointer itself is nil, not the interface.
3. **A struct embeds a pointer to another type to "inherit" its methods**,
   but the embedded pointer is left nil (zero value) in some construction
   path, so calling a promoted method panics on that nil embedded pointer
   even though the outer struct itself is non-nil.
4. **Mixing receiver types inconsistently across a type's own method set**
   (some methods on `T`, some on `*T`) makes it non-obvious which forms
   satisfy which interfaces, especially after a later method is added with
   the "wrong" receiver relative to the existing ones.

## Diagnose
- For the compile-time case, read the exact compiler error -- it names the
  specific method with a pointer receiver that the value type is missing;
  the fix is almost always at the call site (pass `&x` instead of `x`), not
  in the type definition.
- For the runtime nil-interface case, add a print/log of both
  `result == nil` and `fmt.Sprintf("%T", result)` right after the function
  returns -- if `%T` prints a concrete pointer type (not the bare word
  `<nil>`), the interface is non-nil-but-holds-a-nil-pointer, which is the
  classic "typed nil" trap.
- Grep the function that returns the interface type for any `return
  someTypedNilVar` where `someTypedNilVar` was declared as `var x *T` without
  being assigned to a real value on that path -- that's the exact
  construction of a typed nil interface.
- `go vet` flags some but not all instances of this; don't rely on it alone
  -- specifically write a unit test asserting the interface-typed return
  value from the nil-producing code path against `nil` directly to confirm
  whether it behaves as expected.

## Fix
For the method-set mismatch, standardize on pointer receivers for a type the
moment *any* one of its methods needs a pointer receiver (to mutate state, or
to avoid copying a large struct) -- consistency avoids ever needing to reason
about which methods are on which method set, and pass `&T{}` (or a
constructor returning `*T`) everywhere the interface is needed:
```go
type Store struct{ mu sync.Mutex; data map[string]string }
func (s *Store) Get(k string) string { ... } // pointer receiver
// always construct and pass *Store, never Store, where an interface needs Get
```
For the typed-nil-interface trap, never return a bare typed nil pointer as an
interface value when the caller needs to check for "no result" -- return the
literal untyped `nil` explicitly on that path instead of a nil-valued typed
variable:
```go
func find(id string) MyInterface {
    rec := lookup(id)
    if rec == nil {
        return nil // untyped nil interface: caller's != nil check works correctly
    }
    return rec
}
```
For embedded pointers, ensure every construction path (including any default/
zero-value construction) initializes the embedded pointer to a real instance,
or explicitly guard promoted method calls with a nil check on the embedded
field before use.

## Pitfalls
- "Fixing" the compile error by adding a pointer receiver to the interface-
  required method only, while leaving other methods on the value receiver,
  creates a type whose method set is genuinely inconsistent and confusing --
  prefer converting all of the type's methods to pointer receivers together
  once any one of them needs to be.
- Checking `err != nil` on a function returning a custom `error`-implementing
  type by a typed nil pointer hits the exact same trap as the interface case
  above, since `error` is itself an interface -- this is the single most
  common real-world occurrence of this bug class.
- Adding a `reflect.ValueOf(x).IsNil()` check everywhere as a workaround
  handles the immediate symptom but is easy to misuse (panics if `x`'s
  concrete type isn't a nilable kind) -- fixing the root cause (never
  returning a typed nil as the interface) is more robust than defending
  against it downstream.

## Verify
Write a table test that drives the code path known to sometimes return a
"no result" case, and assert with plain `== nil` on the interface-typed
return value (not on the underlying concrete pointer) that it evaluates to
true -- this specifically catches a regression back to returning a typed nil
pointer through an interface return type.
