---
name: lifetime-elision-failure-cannot-infer-appropriate-lifetime
description: Fix a function or struct that fails to compile with "cannot infer an appropriate lifetime" even though the code looks like it should just work.
triggers: ["cannot infer an appropriate lifetime for", "lifetime mismatch error rust", "borrowed value does not live long enough function return", "struct holding a reference wont compile", "explicit lifetime required in this context"]
permissions: ["READ"]
---

## Symptom
A function that takes one or more references and returns a reference (or a
struct that stores a reference) fails to compile with an error like `cannot
infer an appropriate lifetime for autoref due to conflicting requirements` or
`missing lifetime specifier`, pointing at the return type or a struct field
rather than at anything that looks obviously wrong. The code often "should
just work" by inspection -- the actual data clearly outlives its use -- but
the compiler can't see that because lifetime elision rules only cover a
narrow set of shapes.

## Likely causes
1. **Multiple reference parameters with no elision rule that applies** --
   Rust's elision rules only auto-assign an output lifetime when there's
   exactly one input lifetime, or when `&self`/`&mut self` is present. A
   function taking two `&str` parameters and returning `&str` has no rule
   telling the compiler which input the output borrows from, so it must be
   spelled out.
2. **A struct stores a reference without a declared lifetime parameter on the
   struct itself** -- `struct Parser { input: &str }` doesn't compile at all;
   it needs `struct Parser<'a> { input: &'a str }`, and every impl block and
   every place the struct is used then needs to thread that lifetime through.
3. **The returned reference actually borrows from a temporary or a
   locally-owned value**, not from an input parameter at all -- no lifetime
   annotation can fix this because the underlying data really doesn't live
   long enough; the "cannot infer" error is masking a real dangling-reference
   bug, not a syntax gap.
4. **A trait method's default elided lifetime doesn't match what the
   implementor needs**, e.g. implementing a trait with `fn get(&self) -> &T`
   but the concrete type needs to return a reference tied to a different
   input's lifetime than `&self`.

## Diagnose
- Read the exact error span: does it point at a return type, a struct field,
  or an impl block? `rustc --explain E0106` (missing lifetime specifier) or
  `E0621` (explicit lifetime required) gives the precise rule being violated.
- Count the reference parameters in the function signature. If there's more
  than one `&`/`&mut` input and an elided `&` in the output, that's rule #1 --
  elision cannot pick a winner among multiple candidates.
- For struct errors, check whether the struct declaration itself has a
  lifetime parameter (`struct Foo<'a>`) versus the field just using `&T`
  directly -- the latter is always a compile error, not an inference failure.
- For "does not live long enough," trace where the returned reference's value
  is actually created. If it's a `let` binding inside the function body (not
  a parameter, not a field of `&self`), the fix is architectural (return an
  owned value), not a lifetime annotation -- `'static` won't save you here
  and forcing it usually just moves the error to the caller or requires
  leaking memory.

## Fix
Annotate the actual data-flow relationship, not just "whatever makes the
error go away." Name a lifetime and tie it to the specific input the output
really borrows from:
```rust
// Two inputs, elision can't guess which one the output ties to.
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}
```
If the output only ever borrows from one specific parameter, give that
parameter its own lifetime distinct from the others so the signature
documents the real relationship instead of over-constraining unrelated
parameters to share a lifetime:
```rust
fn first_word<'a>(s: &'a str, _config: &Config) -> &'a str { ... }
```
For structs, declare the lifetime on the struct and repeat it on every impl:
```rust
struct Parser<'a> { input: &'a str }
impl<'a> Parser<'a> {
    fn new(input: &'a str) -> Self { Parser { input } }
}
```
When the value genuinely doesn't outlive the function (case 3 above), the
correct fix is to stop returning a reference: return an owned `String`/`Vec<T>`,
or restructure so the caller passes in a buffer/owner that outlives the
borrow. Annotating harder is not an option when the underlying value is
dropped at the end of the function.

## Pitfalls
- Reaching for `'static` to make an error disappear -- it compiles only by
  either leaking memory (`Box::leak`) or because the value already happened
  to be a `'static` literal, and it silently forces every caller to also
  provide `'static` data, which usually just relocates the same error one
  level up the call stack.
- Giving every parameter the same lifetime `'a` "to be safe" when they don't
  actually need to be related -- this over-constrains callers who have two
  references with genuinely different lifetimes and forces them to shorten
  the longer-lived one unnecessarily.
- Adding a lifetime parameter to a struct and then never actually needing it
  because the field could have been an owned type all along -- reference-
  holding structs are viral (every containing struct needs the parameter
  too), so prefer owned data unless the borrow is intentional for
  performance reasons.

## Verify
Run `cargo build` and confirm the specific `E0106`/`E0621`/"does not live long
enough" error is gone, then check the call sites: `cargo doc --open` on the
function/struct and confirm the rendered signature's lifetime relationship
matches your mental model (e.g. the output really is tied to the parameter
you expect). Add a test that exercises the shortest-lived valid input to
confirm the compiler now correctly rejects any caller that tries to use the
returned reference past the borrowed data's scope.
