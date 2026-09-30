---
name: mixed-async-runtime-no-reactor-running-panic
description: Fix a panic like "there is no reactor running" or "no Tokio runtime" caused by mixing tokio and async-std, or calling async code outside any runtime.
triggers: ["there is no reactor running", "no tokio runtime found", "must be called from the context of a tokio runtime", "thread is not currently running a tokio runtime", "async-std and tokio together panic"]
permissions: ["READ"]
---

## Symptom
The program panics at runtime, not compile time, with a message like `there
is no reactor running, must be called from the context of a Tokio 1.x
runtime` or `thread 'main' panicked ... A Tokio 1.x context was found, but
it is being shutdown` or an async-std equivalent. The panic often happens
deep inside a dependency (an HTTP client, a database driver) rather than at
the call site the developer just wrote, and the code "obviously" awaits
inside an async function, which makes the error confusing since async/await
syntax alone gives no compile-time signal about which runtime is required.

## Likely causes
1. **A library was written against a specific runtime's I/O primitives**
   (tokio's `TcpStream`, timers, or task spawning) **but the binary drives
   it with a different runtime**, or with no runtime at all -- the library's
   types need a live reactor of the exact runtime they were built for, and
   Rust's async/await has no built-in mechanism to declare or enforce that
   requirement in the type system.
2. **`tokio::spawn` (or `async_std::task::spawn`) is called from a context
   that isn't inside that runtime's own worker threads** -- e.g. spawning
   from a plain OS thread created with `std::thread::spawn`, a `Drop` impl,
   or a callback invoked by a non-async C library, none of which have a
   runtime context attached.
3. **Two runtimes are both present in the dependency tree** (commonly one
   library pulls in `async-std` while the application uses `tokio`, via a
   transitive dependency), and futures from one are awaited inside the
   other's executor -- the futures compile fine because `Future` is a shared
   trait, but the reactor-dependent parts (timers, sockets) only work under
   their native runtime.
4. **The runtime was shut down or was never entered** -- e.g. `#[tokio::main]`
   was removed or replaced with a manual `Runtime::new()` whose `.block_on()`
   call doesn't actually wrap the code path that panics, so that code runs
   on a thread with no runtime context at all.

## Diagnose
- Read the panic's origin: `RUST_BACKTRACE=1 cargo run` and find which crate
  the panic actually originates in (often visible as `tokio::runtime::...`
  or `async_io::...` frames). That tells you which runtime the failing code
  expects.
- Run `cargo tree -e normal | grep -E "tokio|async-std|async-io|smol"` to see
  whether more than one async runtime is actually being pulled into the
  dependency graph -- a surprising transitive `async-std` or `smol`
  dependency alongside `tokio` is a strong signal of case 3.
- Check every `thread::spawn`, `Drop` implementation, and FFI/C callback in
  the code path leading to the panic for an `async`/`.await`/`tokio::spawn`
  call -- if any of those run outside `#[tokio::main]`'s call tree, that's
  case 2 or 4.
- Confirm the entry point: is `#[tokio::main]` present, or is there a manual
  `Runtime::new().unwrap().block_on(...)`? If the panic happens on code
  reached before or after the `block_on` call (e.g. during setup or in a
  spawned thread that outlives it), the runtime simply isn't active there.

## Fix
Pick one async runtime for the whole binary and verify every dependency that
does real I/O (not just `Future`-returning helper functions) is compatible
with it. For the common tokio case, ensure the runtime is entered for the
entire lifetime of anything that needs it:
```rust
#[tokio::main]
async fn main() {
    // Everything that needs tokio's reactor must run inside this tree.
    run_app().await;
}
```
For code that must spawn work from a non-async context (a plain thread, a
C callback), pass a handle to the already-running runtime explicitly instead
of trying to create a new one implicitly:
```rust
let handle = tokio::runtime::Handle::current();
std::thread::spawn(move || {
    handle.block_on(async {
        do_async_work().await;
    });
});
```
If a dependency hard-requires a different runtime (e.g. it's built on
async-std) and switching it out isn't practical, use a compatibility shim
crate (such as `async-compat` for bridging tokio/async-std I/O) around just
that dependency's calls, rather than mixing runtimes ad hoc throughout the
codebase. When possible, prefer swapping the offending dependency for one
with a tokio-native equivalent -- the shim approach is a bridge, not a
long-term fix, since it adds overhead and doesn't cover every reactor
primitive.

## Pitfalls
- Wrapping every failing call in a fresh `Runtime::new().unwrap().block_on(..)`
  as a local patch -- this creates a brand-new runtime (with its own thread
  pool) per call site, which is expensive, can exhaust OS resources under
  load, and still panics if called from inside an *existing* runtime's
  worker thread (`Cannot start a runtime from within a runtime`).
- Adding `tokio` as a dependency just to get `#[tokio::main]` while leaving
  a transitively-pulled `async-std`-based library in place "because it still
  compiles" -- it compiles because `Future` doesn't encode the runtime
  requirement, but it will panic the first time that library's I/O path
  actually runs.
- Assuming the fix is version-related and bumping tokio's version -- version
  mismatches between two `tokio` majors can cause a similar-looking panic,
  but mixing tokio versions and mixing tokio-with-async-std are different
  root causes with different fixes (unify the version vs. unify the runtime).

## Verify
Run `cargo tree -e normal | grep -E "tokio|async-std|smol|async-io"` again
after the fix and confirm only one runtime family appears (or that the
second one is confined behind a documented compatibility shim). Exercise the
previously-panicking code path under the actual entry point (not a unit test
that calls the function in isolation without `#[tokio::test]` or
`#[tokio::main]`) and confirm no panic occurs. For the thread-spawn case,
specifically test the code path that spawns from a non-async thread to
confirm `Handle::current()` resolves rather than panicking with "no reactor
running".
