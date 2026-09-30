---
name: send-sync-not-satisfied-across-thread-or-await
description: Resolve a compile error that a type does not implement Send or Sync when it is moved across a thread boundary or held across an await point.
triggers: ["future cannot be sent between threads safely", "within this borrow the type is not Send", "Rc<RefCell> cannot be shared between threads safely", "trait bound is not satisfied because it requires Send", "tokio spawn requires Send future"]
permissions: ["READ"]
---

## Symptom
A `tokio::spawn(...)` call, a `std::thread::spawn(...)` call, or a function
with a `Send`/`Sync` bound fails to compile with an error like `future
cannot be sent between threads safely` or `` `Rc<RefCell<T>>` cannot be
shared between threads safely `` or `` within `impl Future`, the trait
`Send` is not implemented for `*mut u8` ``. The error frequently names a
type deep inside the async state machine or a field several layers removed
from anything the developer directly wrote as non-thread-safe, because the
compiler is reporting the *first* non-`Send`/`Sync` type it found while
computing the auto-trait for the whole future or closure, not necessarily
the type that's conceptually the problem.

## Likely causes
1. **An `Rc<T>` or `RefCell<T>` is used somewhere the async task or thread
   closure captures**, directly or transitively -- both are explicitly
   `!Send`/`!Sync` by design (that's the whole point of the cheaper,
   non-atomic reference counting and borrow-flag checking they use), so any
   future or closure that captures one, even through several layers of
   struct fields, becomes non-`Send`.
2. **A `MutexGuard` or `RwLockReadGuard`/`RwLockWriteGuard` (from
   `std::sync`) is held across an `.await` point inside an async function**
   -- these guard types are not `Send` on some platforms/versions and, more
   fundamentally, holding a sync guard across a suspension point is the
   anti-pattern the blocking-executor skill also covers; the compiler
   surfaces it here as a `Send` error on the generated future.
3. **A raw pointer (`*const T`/`*mut T`) is captured by the closure or
   stored in a struct the future holds** -- raw pointers are never `Send`
   or `Sync` automatically (the compiler has no way to know whether the
   pointed-to data is safe to move/share), even if the underlying data
   genuinely would be safe to send.
4. **A third-party type genuinely isn't `Send`/`Sync`-compatible with how
   it's being used** -- e.g. a client object that wraps a non-thread-safe C
   library handle -- and the code is trying to share one instance across
   tasks/threads when the library's design requires one instance per
   thread.

## Diagnose
- Read the error's `required because it appears within the type` chain --
  rustc prints a trail from the outer future/closure down to the specific
  field or captured variable that isn't `Send`/`Sync`. Follow that chain to
  its end rather than stopping at the outermost mention; the real culprit
  is usually the innermost named type.
- If the chain bottoms out at a generated `impl Future` with no obvious
  named type, search the function body for any `Rc`, `RefCell`, `Cell`, or
  raw pointer used between the first `.await` and the point the error
  references -- these are the common non-`Send` primitives that get
  captured into the async state machine.
- Check whether a `MutexGuard` (std, not tokio) is alive across an `.await`
  in the flagged function -- this is visible directly in source as a guard
  variable still in scope when `.await` appears, and is worth checking even
  if the error message doesn't name the guard type explicitly.
- For third-party types, check the crate's docs for explicit `Send`/`Sync`
  guidance -- some types are intentionally `!Send` (e.g. bound to a specific
  OS thread or GUI event loop) and the fix is architectural (route calls to
  it through a channel to its owning thread), not a workaround.

## Fix
Replace the non-`Send`/`Sync` primitive with its thread-safe equivalent when
the data genuinely needs to cross threads: `Rc<T>` becomes `Arc<T>`,
`RefCell<T>` becomes `Mutex<T>`/`RwLock<T>` (or `tokio::sync::Mutex<T>` if
the guard must survive an `.await`), matching the earlier reasoning about
when the async-aware lock is actually needed:
```rust
// Not Send: Rc/RefCell tie this to one thread.
struct State { data: Rc<RefCell<Vec<u8>>> }

// Send + Sync: Arc/Mutex allow safe sharing across threads/tasks.
struct State { data: Arc<Mutex<Vec<u8>>> }
```
For a sync `MutexGuard` held across an `.await`, restructure to drop the
guard before the await point (extract the needed value into an owned local
first), as covered in the deadlock pattern -- this fixes both the `Send`
error and the underlying blocking-executor risk at once.

For raw pointers, wrap the pointer in a newtype and manually implement
`unsafe impl Send`/`unsafe impl Sync` for it *only* after verifying the
invariant that makes it actually safe (e.g. the pointed-to data is never
mutated concurrently, or ownership transfer is exclusive) -- document the
justification in a comment next to the impl, since this bypasses the
compiler's automatic check entirely.

When a type is intentionally thread-bound (case 4), don't force `Send` onto
it -- instead spawn a dedicated task/thread that owns the type exclusively
and communicate with it via an `mpsc` channel, so other tasks send requests
rather than trying to share the object directly.

## Pitfalls
- Slapping `unsafe impl Send for Wrapper<T> {}` on a struct to silence the
  error without checking whether the contained type is actually safe to
  send -- this is a real safety claim to the compiler; if it's wrong, the
  result is a genuine data race that the type system was correctly trying
  to prevent, now only detectable at runtime (if at all).
- Switching `Rc`/`RefCell` to `Arc`/`Mutex` reflexively everywhere in a
  large struct just to satisfy one distant field's `Send` requirement --
  this adds atomic-refcounting and locking overhead to parts of the struct
  that never actually cross a thread boundary; prefer splitting the struct
  so only the genuinely-shared part is wrapped in the thread-safe
  primitives.
- Boxing the future as `Pin<Box<dyn Future<Output = T> + Send>>` to "make
  it Send" without fixing the underlying non-Send capture -- this often
  doesn't compile either (the inner future still isn't Send) or, if it does
  via further workarounds, just hides which specific captured value is the
  actual problem from the next person who hits a similar error.

## Verify
Run `cargo build` and confirm the specific `Send`/`Sync` error is gone with
no new `unsafe impl` added unless it was reviewed and justified in a
comment. If an `unsafe impl Send`/`Sync` was added, run the reproduction
under `cargo +nightly miri test` or with ThreadSanitizer
(`RUSTFLAGS="-Z sanitizer=thread"`) driving concurrent access to confirm no
data race is actually reachable. For the channel-based redesign, add a test
that spawns multiple concurrent callers sending requests to the owning
task/thread and confirm responses come back correctly under concurrent load.
