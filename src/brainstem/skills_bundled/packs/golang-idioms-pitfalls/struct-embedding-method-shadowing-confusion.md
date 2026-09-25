---
name: struct-embedding-method-shadowing-confusion
description: Untangle unexpected behavior when an outer struct's embedded field method gets silently shadowed or ambiguously promoted after adding a same-named method.
triggers: ["embedded struct method not being called", "ambiguous selector embedding", "wrong method called after embedding", "struct embedding shadowed method", "promoted method calling unexpected implementation"]
permissions: ["READ"]
---

## Symptom
A struct embeds one or more other types to "inherit" their methods, and one
of three confusing things happens: (1) after adding a method to the outer
struct with the same name as one on the embedded type, callers who expected
the embedded type's behavior silently get the outer struct's method instead
(no compile error, no warning); (2) after embedding a *second* type that
happens to define a same-named method as the first embedded type, the
compiler now rejects the previously-fine `outer.Method()` call with an
"ambiguous selector" error; or (3) a method promoted from an embedded type
calls another method by name expecting dynamic dispatch to the outer struct's
override, but instead always calls the embedded type's own version, because
Go embedding is not inheritance and has no virtual dispatch.

## Likely causes
1. **A method is added to the outer struct with the same name as a promoted
   method from an embedded field**, intending to "extend" or "customize" the
   embedded behavior -- Go silently shadows the embedded method at the
   outer level (shallower depth wins), with zero compiler diagnostic, so any
   existing call site through the outer struct value now silently gets
   different behavior than before the addition.
2. **Two embedded fields at the same depth define a method with the same
   name**, and code calls it through the outer struct without qualifying
   which embedded field's version it means -- this is a compile error
   ("ambiguous selector"), but it often only surfaces after a *second*
   embedded type is added later, breaking previously-working call sites
   far from the actual change.
3. **Code assumes embedding gives inheritance-style dynamic dispatch**, where
   an embedded type's method calling `self.Other()` would resolve to an
   overriding method on the outer struct -- Go embedding is pure struct
   composition plus method promotion; a method defined on the embedded type
   only ever calls other methods on that same embedded type, never a
   "subclass override," because the embedded type has no notion that it's
   embedded in anything.
4. **Embedding a type for its methods while also embedding it (or another
   type sharing field names) for its fields**, creating similar ambiguity or
   shadowing for field access, not just methods, which is easy to overlook
   when reasoning only about the method-promotion angle.

## Diagnose
- Run `go build`/`go vet` first -- the ambiguous-selector case (cause 2) is
  always a hard compile error naming the ambiguous field/method, so it's
  never a silent runtime mystery; if the bug report describes a compile
  error, it's this case.
- For the silent-shadowing case (cause 1, no compile error), grep both the
  outer struct and every embedded type for methods sharing the exact same
  name -- any match is a shadow, and the outer struct's version always wins
  when called through the outer struct's own value or pointer.
- For the "expected override to take effect" case (cause 3), check whether
  the method that isn't dispatching as expected is called *from within
  another method defined on the embedded type itself* (`func (e Embedded)
  Foo() { e.Bar() }`) rather than from outside -- if so, `e.Bar()` always
  resolves statically to `Embedded.Bar`, never to an outer struct's `Bar`
  override, regardless of what the outer struct looks like at the call site.
- Use `go doc <pkg>.<OuterType>` or an IDE's "go to definition" on the
  specific call site in question to see exactly which method Go resolved the
  call to -- this disambiguates shadowing confusion faster than reading the
  struct definitions by eye, especially with multiple embedding levels.

## Fix
When the outer struct genuinely needs to customize behavior an embedded
type provides, don't rely on silent method shadowing to communicate that --
name the outer method distinctly, or make the customization explicit by
having the outer method call the embedded one deliberately by its qualified
name so the relationship is visible in the code, not just in method-set
rules:
```go
type Base struct{}
func (b Base) Describe() string { return "base" }

type Wrapper struct{ Base }
// explicit override that documents intent and still reaches the original:
func (w Wrapper) Describe() string {
    return "wrapped: " + w.Base.Describe()
}
```
For the "expected dynamic dispatch" case, Go has no built-in virtual method
mechanism through embedding -- if that's genuinely the needed shape (an
overridable template-method pattern), model it explicitly with an interface
field the base type calls through, not embedding:
```go
type Describer interface{ Describe() string }
type Base struct{ Impl Describer } // explicit "self" reference
func (b Base) Report() string { return "report: " + b.Impl.Describe() }
```
For ambiguous selectors from two same-named embedded methods, qualify the
call explicitly (`outer.FieldA.Method()`) at every ambiguous call site, or
rename/wrap one of them at the outer level to remove the ambiguity for good.

## Pitfalls
- Renaming the outer struct's method to avoid a shadow collision but not
  updating existing callers who depended on the (now-shadowed) embedded
  behavior under the original name -- audit every call site through the
  outer type, not just the definition, since shadowing is silent and
  compiles cleanly either way.
- Assuming embedding an interface (not a concrete struct) behaves
  differently regarding shadowing -- it doesn't; the same shallowest-depth-
  wins and ambiguous-selector rules apply whether the embedded field is a
  concrete type or an interface type.
- Deep multi-level embedding chains (a struct embedding a struct embedding
  another struct) make shadowing and promotion depth genuinely hard to trace
  by eye -- prefer flat, single-level embedding, or explicit delegation
  methods, once more than two levels are involved.

## Verify
Write a table test that constructs the outer struct and calls the
potentially-shadowed method name directly, asserting the result matches
whichever behavior is actually intended (outer override or embedded
original) -- then deliberately add a second embedded type with a colliding
method name in a throwaway branch to confirm it produces a compile-time
ambiguous-selector error rather than silently picking one, verifying your
understanding of which case you're in.
