---
name: async-drop-cancellation-leaves-work-half-done
description: Diagnose state left half-updated or a resource left uncleaned because an in-flight async task was cancelled mid-await when its future was dropped.
triggers: ["tokio select cancelled task left state inconsistent", "future dropped mid await leaves data corrupt", "timeout cancels task but resource never released", "abort_handle leaves lock held", "cancel safety rust async"]
permissions: ["READ"]
---

## Symptom
A task driven by `tokio::select!`, `.abort()`, or a timeout wrapper
(`tokio::time::timeout`) is cancelled partway through, and afterward some
downstream state is left inconsistent: a database row is half-updated, a
file is left truncated, a semaphore permit or lock is never released, or a
counter is incremented without its matching decrement ever running. Nothing
panics -- the future is simply dropped mid-poll -- which makes this look
like a logic bug in the task's own code rather than what it actually is:
Rust async cancellation is "drop the future," not "run to a safe exit
point," and code that isn't written to be cancel-safe at every `.await`
silently loses whatever cleanup was supposed to happen after the point it
was cancelled.

## Likely causes
1. **A multi-step operation awaits several steps in sequence with no
   cancellation-safe undo/commit boundary** -- e.g. `write_header().await;
   write_body().await;` -- if the future is dropped between the two awaits
   (the branch lost a `tokio::select!` race, or a timeout fired), the header
   is written but the body never will be, and nothing runs to detect or
   roll that back.
2. **A guard/permit is acquired before an `.await` that can be cancelled,
   with the intended release logic written as a later explicit statement**
   instead of relying on `Drop` -- if the future is dropped before reaching
   that explicit release code, the release never executes; relying on an
   explicit "then release" step rather than a `Drop` impl is the actual gap
   (the guard's own `Drop` would still run correctly on cancellation --
   the bug is when release logic is *not* tied to a value's `Drop`, e.g. a
   manual counter decrement written as a later `.await`-separated
   statement).
3. **`tokio::select!`'s documented behavior is misunderstood** -- the
   losing branches' futures are dropped, not paused and resumable, so code
   assuming "the other branch will just continue next time" is wrong; any
   partial side effects the losing branch already performed (before its own
   drop point) already happened and won't be undone automatically.
4. **`.abort()` is called on a `JoinHandle` for a task performing
   non-idempotent external side effects** (an API call already sent, a
   partial write already flushed) -- aborting stops the task's *Rust-level*
   execution at its next await point, but cannot undo an external effect
   that already happened before that point, so "abort" is not equivalent to
   "guarantee nothing happened."

## Diagnose
- Identify every `.await` point in the cancellable task and ask, for each
  one individually: "if this future is dropped right after this await
  resolves but before the next line runs, what state have I left behind?"
  This must be done per-await, not just once for the whole function, since
  cancellation can land at any of them.
- Check whether resource release (locks, permits, temp file cleanup,
  counters) is implemented via a `Drop` impl on a guard/RAII type, versus a
  bare explicit statement later in the function -- `Drop`-based cleanup
  runs even on cancellation (dropping the future drops its live local
  variables, which runs their `Drop` impls); a later explicit statement
  does not run if cancellation happens before reaching it.
- Grep for `tokio::select!`, `tokio::time::timeout`, and `.abort()` call
  sites and, for each, read what work the cancelled branch/task does before
  its first (or next) `.await` -- any side effect performed there already
  happened and needs to be accounted for as a possible outcome, not
  assumed away.
- Reproduce deliberately: wrap the suspect operation in
  `tokio::time::timeout(Duration::from_millis(1), op())` in a test to force
  frequent mid-flight cancellation, then inspect the resulting state for
  the inconsistency (partial write, unreleased permit) that production only
  hit intermittently.

## Fix
Make cleanup cancellation-safe by tying it to a value's `Drop` impl (an RAII
guard) instead of a later explicit statement, since `Drop` runs
unconditionally when the future (and its live locals) are dropped:
```rust
struct PermitGuard<'a>(&'a Semaphore);
impl Drop for PermitGuard<'_> {
    fn drop(&mut self) { self.0.release(); } // runs even if cancelled mid-await
}
async fn do_work(sem: &Semaphore) {
    let _guard = PermitGuard(sem); // acquired before any cancellable await
    risky_operation().await; // if cancelled here, _guard still drops and releases
}
```
For multi-step operations that must be atomic from an external observer's
point of view, restructure so partial progress is either invisible until a
final commit step, or is itself idempotent/resumable -- e.g. write to a
temp file and rename atomically at the end rather than writing pieces of
the destination file directly, so a cancellation mid-write never leaves the
destination half-written. For operations that can't be made atomic (an
external API call that isn't idempotent), make the *task*, not just the
future, own the decision to cancel: use a cooperative cancellation flag
checked only at safe boundaries, rather than relying on `select!`/`abort()`
to interrupt at an arbitrary point.

## Pitfalls
- Assuming `tokio::select!`'s losing branch "pauses" and can be resumed
  later -- it's dropped, not paused; any state it needs must either survive
  in a variable owned outside the `select!` or be re-derived from scratch
  next time.
- Adding a `Drop` impl for cleanup but having it perform its own `.await`-
  requiring work (`Drop::drop` is synchronous only) -- async cleanup on
  drop isn't directly expressible; the common workaround (spawning a
  detached cleanup task from `drop()`) needs its own accounting since it's
  now an untracked, fire-and-forget operation with its own failure modes.
- Treating `.abort()` as equivalent to a guaranteed rollback -- it stops
  further polling but does nothing about side effects already committed
  before the abort took effect; code that needs true rollback must
  implement it explicitly (compensating actions, idempotency keys), not
  assume `.abort()` provides it.

## Verify
Run the forced-cancellation test (wrapping the operation in a very short
`tokio::time::timeout` or racing it against an immediately-ready future in
`select!`) in a loop across many iterations and assert the invariant that
matters (permit count returns to baseline, no partial file is left, a
counter never goes negative) holds after every cancelled run, not just the
happy-path completion case. For lock/permit guards specifically, assert
`Semaphore::available_permits()` (or equivalent) returns to its starting
value after a batch of deliberately-cancelled operations.
