---
name: pin-self-referential-future-compile-error
description: Resolve a confusing Pin-related compile error when manually implementing a Future or storing a self-referential async state machine.
triggers: ["cannot be unpinned error rust", "Pin<Box<Self>> confusing error", "manually implementing Future trait error", "self-referential struct future wont compile", "PhantomPinned required for this type"]
permissions: ["READ"]
---

## Symptom
Code that manually implements `Future` (rather than writing an `async fn`
and letting the compiler generate the state machine), or that tries to
store a struct which borrows from its own field, fails to compile with
errors mentioning `Pin`, `Unpin`, or `` `T` cannot be unpinned ``, often
pointing at a `poll` method signature or a struct definition that "should"
just work by normal ownership rules. This surfaces most often when writing
a custom combinator future, integrating with a C library via FFI that needs
a stable address, or building a hand-rolled async state machine instead of
relying on `async fn`'s compiler-generated one (which handles `Pin`
correctly without the author ever seeing it).

## Likely causes
1. **A struct is defined to hold both a value and a reference/pointer into
   that same value** (the classic self-referential struct) -- ordinary Rust
   references can't express this because moving the struct would invalidate
   the internal reference; `Pin` exists specifically to make a guarantee
   ("this value's address won't change") that self-referential types can
   rely on, and hitting a `Pin`/`Unpin` error while attempting this pattern
   usually means the code is trying to do it without going through `Pin`'s
   actual machinery.
2. **A manual `Future` impl's `poll` method tries to get `&mut` access to
   fields through `Pin<&mut Self>` the same way it would through a plain
   `&mut Self`**, without using `Pin::as_mut()`/projection helpers (or the
   `pin-project` crate) -- naive field access through a pinned reference
   doesn't compile because `Pin` deliberately restricts safe `&mut` access
   to prevent moving pinned data out from under itself.
2. **A generated `async fn` state machine captures a local variable and then
   also captures a reference to that same local across an `.await` point**
   (e.g. `let buf = [0u8; 4]; let r = &buf; something(r).await;`) -- this is
   exactly the self-referential shape, and it's what makes `async fn`'s
   compiler-generated future require `Pin` at all; the error usually
   appears not in the async function itself (which compiles fine) but where
   the resulting future is used without being pinned, e.g. passed to
   something expecting `Unpin`.
3. **Code tries to move a value out of a `Pin<&mut T>` or `Pin<Box<T>>`**
   (e.g. via `std::mem::replace`, `swap`, or destructuring) for a type that
   isn't `Unpin` -- this is exactly the operation `Pin` exists to forbid for
   non-`Unpin` types, since moving it could invalidate internal
   self-references.

## Diagnose
- Identify whether the type in question is hand-written to be
  self-referential (a struct with both an owned field and a reference/raw
  pointer into it) versus a compiler-generated `async fn` future being used
  incorrectly -- the fix differs substantially between the two.
- For manual `Future` implementations, check whether field access inside
  `poll(self: Pin<&mut Self>, ...)` uses direct `self.field` mutation or
  goes through a pin-projection pattern -- direct mutation of a field behind
  `Pin<&mut Self>` without projection is the most common compile error
  source here, and `rustc --explain` on the specific `E0XXX` code given
  will state exactly which operation isn't permitted.
- For the "future isn't Unpin" case, check the function signature or trait
  bound that's rejecting it (often a channel, a `JoinHandle`, or a
  combinator expecting `Unpin`) -- most such APIs actually accept any
  `Future` once it's wrapped in `Box::pin(fut)` or `tokio::pin!(fut)`, so
  confirm whether the real fix is just pinning at the call site rather than
  changing the future's definition.
- If genuinely building a self-referential type, check whether the
  `pin-project` or `pin-project-lite` crate is already a dependency -- these
  provide safe, audited field-projection macros and are the standard way to
  implement this pattern without hand-writing `unsafe` pin projections.

## Fix
For the common case -- a future that isn't `Unpin` needs to be used
somewhere requiring it -- pin it at the use site rather than trying to make
the type itself `Unpin`:
```rust
let fut = some_async_fn(); // not Unpin, e.g. captures a self-reference internally
tokio::pin!(fut); // now usable as Pin<&mut _> where Unpin was required
fut.as_mut().poll(cx);
```
or, for an owned, heap-allocated pinned future: `let fut: Pin<Box<dyn Future<Output = T>>> = Box::pin(some_async_fn());`.

For manually implementing `Future` on a struct with multiple fields that
need independent `&mut` access inside `poll`, use `pin-project` to generate
safe projection instead of hand-writing `unsafe` pointer arithmetic:
```rust
use pin_project::pin_project;
#[pin_project]
struct Combined<F1, F2> { #[pin] a: F1, #[pin] b: F2 }
impl<F1: Future, F2: Future> Future for Combined<F1, F2> {
    type Output = (F1::Output, F2::Output);
    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        let this = self.project(); // safe, generated field projection
        // this.a: Pin<&mut F1>, this.b: Pin<&mut F2>
        todo!()
    }
}
```
For a genuinely self-referential struct outside the `Future` context,
prefer avoiding self-reference entirely first (store an index/offset
instead of a pointer into your own buffer, or use `Rc`/`Arc` to share
ownership rather than borrowing from yourself) -- only reach for manual
`Pin` + `unsafe` construction (with `PhantomPinned` marking the type as
`!Unpin`) when no such restructuring is possible, and treat that as
`unsafe`-code territory requiring the same rigor (safety comments, Miri
testing) as any other `unsafe` block.

## Pitfalls
- Implementing `Unpin` manually (or removing a `PhantomPinned` marker) just
  to make an error disappear, for a type that's actually self-referential --
  this is a soundness bug waiting to happen: it tells the compiler the type
  is safe to move freely, which for a genuinely self-referential type
  allows exactly the invalidation `Pin` exists to prevent, surfacing later
  as UB rather than a compile error.
- Reaching for `unsafe { Pin::new_unchecked(&mut x) }` to sidestep a `Pin`
  requirement without verifying `x` will never move afterward -- this
  bypasses the compiler's own check of the very invariant `Pin` encodes,
  and any violation is a silent soundness bug, not a panic.
- Hand-writing pin projection logic instead of using `pin-project` "to avoid
  a dependency" -- manual pin projection has subtle soundness requirements
  (not moving a field you've projected as `!Unpin`, correctly handling
  `Drop`) that are easy to get wrong; the crate exists because this is a
  known hard-to-hand-roll-correctly pattern.

## Verify
Run `cargo build` and confirm the `Pin`/`Unpin` error is resolved without
any new `unsafe` block added, unless that block has a reviewed `// SAFETY:`
comment. If a self-referential type was built with `pin-project`, run
`cargo +nightly miri test` against it to catch any remaining soundness
issue the macro's generated code doesn't already guarantee away. For a
manual `Future` impl, add a test that polls it manually (not just via
`.await` in an async test) through multiple `Poll::Pending` cycles to
confirm state is correctly preserved across polls, since that's the
behavior `Pin` was protecting.
