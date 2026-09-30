---
name: interface-return-type-forces-type-assertion
description: Refactor a function that returns an interface type instead of a concrete struct, forcing callers into awkward type assertions and hiding useful methods.
triggers: ["function returns interface but callers need concrete methods", "type assertion after calling constructor", "why does this return an interface not a struct", "cannot access field on interface return value", "unnecessary interface return type"]
permissions: ["READ"]
---

## Symptom
A constructor-like function (often named `New...`) or a factory method
returns an interface type (e.g. `func NewClient() ClientInterface`) even
though there is exactly one concrete implementation in the entire codebase.
Callers that need a method or field not on the interface -- often added later
for a specific use case -- resort to `c.(*concreteClient)` type assertions to
get at it, and every call site pays for an extra layer of indirection and a
slightly larger allocation just to satisfy an interface nothing actually
varies through.

## Likely causes
1. **Cargo-culting "program to an interface, not an implementation" as a
   blanket rule applied at the point of construction**, rather than at the
   point of *consumption* -- Go's idiom is for the *caller* (or the package
   that needs to accept multiple implementations) to define the interface it
   needs, not for the producing package to pre-emptively wrap its own single
   concrete type.
2. **A single implementation was later joined by a second one (e.g. a mock
   for tests), and the interface was introduced at the constructor return
   type instead of narrowly at the test seam**, so all production call sites
   now pay the interface indirection cost for a distinction that only matters
   inside test code.
3. **Copying a design pattern from another language (Java/C# style "return
   the interface type from the factory") without accounting for Go's
   implicit interface satisfaction** -- in Go, any caller that wants to
   accept multiple types can already declare its own minimal interface
   without the producing package needing to expose one at all.
4. **A later feature needed a method that exists only on the concrete type**,
   and instead of widening the interface (or reconsidering whether the
   interface should exist at all), a type assertion was added at the one call
   site that needed it, and this became the accepted pattern for every
   subsequent similar need.

## Diagnose
- Grep the codebase for the interface's name and count concrete
  implementations (`grep -rn "ClientInterface" .` plus checking how many
  types have `var _ ClientInterface = (*T)(nil)` style assertions, or simply
  how many struct types implement its full method set) -- one implementation
  in non-test code is the strong signal this interface shouldn't be the
  return type.
- Grep for type assertions on the interface's variable name at call sites
  (`\.\(\*concreteType\)` patterns) -- each one is a symptom of a caller that
  needed something the interface didn't expose, and is direct evidence the
  interface is the wrong boundary.
- Check whether the interface is defined in the *producing* package
  (alongside the concrete type) versus a *consuming* package -- Go convention
  favors interfaces declared where they're consumed; one declared next to its
  sole implementation and returned from that same package's constructor is
  the textbook antipattern (sometimes called the "usually unnecessary"
  interface per Go's own style guidance).
- Search for `_test.go` files implementing the interface -- if the *only*
  second implementation is a hand-rolled mock, that's a sign the interface
  exists purely for testability and should be scoped to the test seam (or
  replaced with a concrete-type-based fake/`httptest`-style test double)
  rather than baked into the production return type.

## Fix
Return the concrete type from the constructor, and let any package that
genuinely needs to accept more than one implementation declare its own
narrow interface at the point of use (the consumer defines the contract it
needs, not the producer):
```go
// producing package: return the concrete type
func NewClient(cfg Config) *Client { return &Client{cfg: cfg} }
func (c *Client) Do(req Request) (Response, error) { ... }
func (c *Client) Close() error { ... } // now directly accessible, no assertion

// consuming package that genuinely needs to swap implementations (e.g. tests)
type doer interface { Do(req Request) (Response, error) }
func Process(d doer, req Request) error { ... } // accepts *Client or a test double
```
This keeps the concrete type's full API available to every caller by
default, and only introduces an interface exactly where substitutability is
actually needed, scoped as narrowly as that need requires (often a
single-method interface).

## Pitfalls
- Swinging too far the other way and eliminating every interface, including
  ones that genuinely have multiple real implementations (e.g. `io.Writer`-
  style sinks, pluggable storage backends) -- the rule is "don't return an
  interface with exactly one implementation for no consumer-driven reason,"
  not "never use interfaces at the boundary."
- Changing a widely-used exported constructor's return type from an interface
  to a concrete type is a breaking API change for any external module already
  depending on the interface type in its own signatures -- this refactor is
  cheap inside a single module/monorepo but needs a deprecation path for a
  published library.
- Introducing the narrow consumer-side interface but naming it after the
  concrete type instead of the behavior it needs (e.g. `ClientInterface`
  instead of `doer` or `requester`) reproduces the same "interface shadows a
  single struct" smell one level down.

## Verify
After the change, grep for the old interface name and confirm the only
remaining occurrences (if any) are narrowly-scoped, consumer-defined
interfaces with a real second implementation (production or test) -- not a
producer-side interface with one implementation. Confirm `go build ./...`
succeeds with the constructor returning the concrete type and that any
previously-necessary type assertions at call sites have been deleted, not
merely relocated.
