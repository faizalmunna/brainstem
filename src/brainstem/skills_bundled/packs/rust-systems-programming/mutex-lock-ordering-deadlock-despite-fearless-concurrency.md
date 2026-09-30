---
name: mutex-lock-ordering-deadlock-despite-fearless-concurrency
description: Diagnose a Mutex or RwLock deadlock from inconsistent lock acquisition order that Rust's type system compiled cleanly despite it, contradicting "fearless concurrency" expectations.
triggers: ["deadlock rust mutex", "program hangs forever no panic no error", "rwlock deadlock", "two threads waiting on each other's lock", "fearless concurrency didnt stop this deadlock"]
permissions: ["READ"]
---

## Symptom
A multi-threaded Rust program using `std::sync::Mutex`, `RwLock`, or an
async equivalent (`tokio::sync::Mutex`) simply hangs -- no panic, no error,
CPU usage often drops near zero -- typically under concurrent load or a
specific interleaving that doesn't reproduce every run. It compiled without
warnings, which surprises developers who associate Rust's ownership system
with "fearless concurrency" and expect the compiler to have ruled this out;
in reality Rust's borrow checker guarantees memory safety (no data races)
but says nothing about lock *ordering*, so a classic deadlock is fully
expressible and compiles cleanly.

## Likely causes
1. **Two code paths acquire the same two locks in opposite order** -- thread
   A locks `mutex_x` then `mutex_y`, thread B locks `mutex_y` then
   `mutex_x`; if both reach their second lock call before either releases
   its first, both wait forever. This is the textbook lock-ordering
   deadlock and is invisible to the type system entirely.
2. **A function re-acquires a lock it (or its caller) is already holding**
   -- calling `self.lock().unwrap()` inside a method that's called from
   another method which already holds that same `Mutex`'s guard. `std::sync::Mutex`
   is not reentrant, so this deadlocks the single thread against itself
   (not even a race with another thread required).
3. **A `MutexGuard` is held across an `.await` point** in async code,
   and the task yields while still holding the lock; if the executor
   schedules another task on the same thread that needs the same lock
   before the first task is polled again, that thread deadlocks against
   itself since a synchronous `Mutex` guard held across an await doesn't
   get released just because the task suspended.
4. **A `RwLock` reader upgrade pattern** -- code holds a read guard and then
   tries to acquire a write guard on the same lock before dropping the read
   guard (common when a function takes `&self` under a read lock and
   internally tries to mutate via a write lock) -- most `RwLock`
   implementations are not reentrant/upgradeable, so this deadlocks even on
   a single thread with no contention from anyone else.

## Diagnose
- Attach a debugger (`gdb`/`lldb`, or on Linux `sudo gdb -p <pid>`) to the
  hung process and get a backtrace of every thread (`thread apply all bt`).
  Threads parked inside `pthread_mutex_lock`/`__lll_lock_wait` (or
  `parking_lot`/`std::sync` internals) pinpoint exactly which locks are
  contended and from which call sites.
- Grep every function that takes `&self` and internally calls
  `.lock()`/`.read()`/`.write()` for calls to *other* methods on the same
  type that also lock -- this surfaces the single-thread reentrant case
  (#2, #4) by inspection without needing reproduction.
- For the async case, search for `.lock().await` or a held `MutexGuard`
  whose scope spans another `.await` call within the same block -- this is
  visible directly in the source: if a guard variable is still in scope
  when an `.await` appears, that's the smoking gun. `tokio::sync::Mutex`'s
  guard is `Send` specifically to allow holding it across awaits, which
  makes it easy to do by accident without any compiler warning.
- If reproduction is inconsistent, run under `parking_lot`'s deadlock
  detection feature (`parking_lot = { features = ["deadlock_detection"] }`)
  or add a background thread that periodically calls
  `parking_lot::deadlock::check_deadlock()` and logs any cycles found --
  this directly names the cycle of threads/locks instead of requiring
  manual backtrace correlation.

## Fix
Establish and document a single, global lock acquisition order for any pair
of locks that are ever held simultaneously, and enforce it structurally
rather than by convention alone -- e.g. always lock in a fixed field
declaration order, or wrap both locks behind one accessor that only ever
exposes the correct order:
```rust
// Always acquire in this order everywhere in the codebase.
fn transfer(a: &Mutex<Account>, b: &Mutex<Account>) {
    let (first, second) = if std::ptr::eq(a, b) { return; }
        else if (a as *const _ as usize) < (b as *const _ as usize) { (a, b) } else { (b, a) };
    let mut guard1 = first.lock().unwrap();
    let mut guard2 = second.lock().unwrap();
    // ... now safe regardless of caller's argument order
}
```
For the reentrant case, restructure so the outer function does the locking
and passes an already-unlocked value (or the guard itself) into the inner
function, rather than having the inner function lock again:
```rust
fn update(&self) {
    let mut data = self.data.lock().unwrap();
    self.apply(&mut data); // takes &mut T, does not lock again
}
```
For async code, scope the guard explicitly to end before any `.await`,
using a block to force the drop:
```rust
{
    let mut guard = self.state.lock().await;
    guard.count += 1;
} // guard dropped here, before the next .await
some_async_call().await;
```
For the `RwLock` upgrade case, drop the read guard before acquiring the
write guard rather than assuming an implicit upgrade path, or use a lock
type that explicitly supports upgradable reads (e.g. `parking_lot::RwLock::upgradable_read`)
if the upgrade is genuinely needed.

## Pitfalls
- Reaching for more `Mutex`es to "isolate" the problem when the real issue
  is ordering between the ones that already exist -- more locks without a
  documented order just gives the deadlock more ways to happen.
- Fixing a specific deadlock by adding a timeout (`try_lock` with a sleep
  loop) instead of fixing the ordering -- this converts a hang into
  silent, intermittent data corruption or dropped work when the timeout
  fires mid-operation, which is harder to detect than an outright hang.
- Assuming `tokio::sync::Mutex` is a drop-in replacement for
  `std::sync::Mutex` "to fix async deadlocks" without addressing why a
  guard was held across an await in the first place -- it avoids blocking
  the OS thread, but a lock-ordering deadlock between two `tokio::sync::Mutex`
  instances is just as possible as with the std version.

## Verify
Reproduce the original hang under a stress test that drives the two code
paths concurrently with a tight loop (e.g. `loop { transfer(&a, &b); }` and
`loop { transfer(&b, &a); }` on separate threads for a fixed duration) and
confirm it now completes instead of hanging, ideally under a CI job with a
hard timeout so a regression fails loudly instead of hanging the pipeline.
If using `parking_lot`'s deadlock detection during development, confirm
`check_deadlock()` reports zero cycles after the fix under the same stress
scenario that previously triggered one.
