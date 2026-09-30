---
name: rc-refcell-clone-overuse-runtime-borrow-panic
description: Fix a "already borrowed" or "already mutably borrowed" panic caused by routing around ownership friction with Rc<RefCell<>> instead of fixing the design.
triggers: ["already borrowed: BorrowMutError", "already mutably borrowed: BorrowError", "RefCell panic at runtime", "Rc RefCell everywhere anti-pattern", "borrow checker workaround causes panic instead of compile error"]
permissions: ["READ"]
---

## Symptom
The program compiles fine -- often after a round of "just wrap it in
`Rc<RefCell<T>>`" to silence borrow checker errors -- but then panics at
runtime with `already borrowed: BorrowMutError` or `already mutably
borrowed: BorrowError`, usually deep in a call chain far from where the
`.borrow()`/`.borrow_mut()` that triggered it was written. The frustrating
part is that this is strictly worse than the original compile error: the
borrow checker used to catch the conflict for free at compile time, and
now the same class of conflict only surfaces when the exact code path runs,
possibly only under specific input or ordering in production.

## Likely causes
1. **A method holds a `borrow()`/`borrow_mut()` guard while calling another
   method (directly or via callback) that also needs to borrow the same
   `RefCell`** -- e.g. iterating over `self.borrow().children` and, inside
   the loop, calling something that also does `self.borrow_mut()`. This is
   the same reentrancy shape as the original borrow-checker error, just
   deferred to runtime because `RefCell` moved the check there.
2. **`Rc<RefCell<T>>` was reached for as a first response to a borrow
   checker error without checking whether the data actually needs shared,
   mutable, multi-owner access** -- often a single-owner tree or list got
   this treatment because it was the fastest way to make one specific error
   disappear, and now every consumer of that type has to borrow it, spreading
   the panic risk throughout the codebase.
3. **A callback or observer pattern stores an `Rc<RefCell<T>>` and invokes
   the callback from inside code that already holds a borrow on the same
   `T`** -- common in event-emitter-style designs where "notify observers"
   is called from within a method that mutated `self` and still holds the
   guard.
4. **Cloning the `Rc` (cheap, just bumps a refcount) is confused with
   cloning the underlying data** -- code assumes each `Rc::clone()` gives an
   independent copy safe to mutate concurrently, when in fact all clones
   point at the same `RefCell`, so "independent-looking" mutations from
   different call sites are actually the same reentrancy hazard.

## Diagnose
- Get the panic backtrace (`RUST_BACKTRACE=1`) and find both the
  `.borrow_mut()`/`.borrow()` call that panicked and, walking up the stack,
  the outer call that's still holding a guard on the same `RefCell` --
  they're often in the same function or one call away, once you know to
  look for a live guard variable still in scope.
- Grep the type for every `.borrow()` and `.borrow_mut()` call site and
  check whether any of them call a method (or invoke a stored closure) that
  itself borrows the same cell before the first guard's scope ends -- this
  finds the reentrancy statically without needing to hit the exact panic
  condition at runtime.
- Ask, for each `Rc<RefCell<T>>` in the codebase: is `T` ever actually
  observed by more than one owner concurrently, or is there really a single
  logical owner and the `Rc` was only added to dodge a borrow error? If
  `Rc::strong_count()` is checked at a few points and never exceeds 1-2 in
  practice, that's a signal the sharing was never needed.
- Check whether the guard is being held across a loop body that calls into
  application code (not just simple field access) -- long-lived guards
  across loops or callbacks are the most common trigger.

## Fix
First ask whether `Rc<RefCell<T>>` is even necessary: if there's truly one
owner, prefer plain ownership and `&mut` borrows, or restructure per the
ownership-redesign pattern (splitting a self-referential struct, or using
index-based references into a `Vec`/arena) so the borrow checker can verify
the access pattern at compile time again. That is almost always a better
fix than tuning the runtime borrow pattern.

When shared, interior-mutable access is genuinely required (e.g. a real
multi-owner graph, or a callback registry), scope every borrow as narrowly
as possible and never call back into code that might re-borrow while a
guard is alive:
```rust
// Bad: guard alive across a call into code that also borrows.
let mut inner = self.state.borrow_mut();
inner.children.iter().for_each(|c| c.notify()); // notify() may borrow_mut self.state

// Better: copy out what's needed, drop the guard, then call out.
let children: Vec<_> = self.state.borrow().children.clone();
for c in children { c.notify(); }
```
Where possible, replace the observer/callback shape with one that returns
events/commands instead of directly re-entering the mutable state, so the
caller applies mutations after the borrow is dropped rather than the
callback reaching back in.

## Pitfalls
- Swapping `RefCell` for `Mutex` "to make it thread-safe" without addressing
  the reentrancy -- a `std::sync::Mutex` is also not reentrant, so the exact
  same call pattern that panics with `RefCell` will deadlock (hang, not
  panic) with a `Mutex` on a single thread, which is often harder to debug
  than a clear panic message.
- Wrapping the panic site in `try_borrow_mut()` and silently skipping the
  operation on failure -- this hides the reentrancy bug instead of fixing
  it, and produces silently-dropped mutations that are far harder to
  diagnose than a loud panic.
- Adding `Rc<RefCell<>>` around a field "just in case it's needed later" --
  every additional layer makes the type harder to reason about and adds
  runtime overhead (refcounting, borrow-flag checks) for flexibility that
  may never be used; add it when a second owner actually exists, not
  preemptively.

## Verify
Reproduce the panic's exact call sequence in a unit test first (a test that
calls the outer method with the same nested-callback shape) and confirm it
now completes without panicking. Then grep the type for any remaining
`Rc<RefCell<>>` fields and confirm each one has a real multi-owner
justification (e.g. a comment or a test with more than one live `Rc::clone`)
-- any that don't should be converted back to plain ownership. Run the
existing test suite plus `cargo clippy` to catch any newly-dead
`Rc`/`RefCell` imports left over from the simplification.
