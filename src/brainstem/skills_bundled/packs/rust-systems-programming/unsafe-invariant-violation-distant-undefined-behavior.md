---
name: unsafe-invariant-violation-distant-undefined-behavior
description: Trace undefined behavior such as corrupted data or a segfault back to an unsafe block that violated an aliasing or initialization invariant far upstream.
triggers: ["segfault in safe rust code", "undefined behavior far from unsafe block", "miri detected undefined behavior", "data looks corrupted for no reason", "unsafe code works until release mode"]
permissions: ["READ"]
---

## Symptom
The program crashes (segfault, `SIGILL`, or a mysteriously wrong value)
inside code that is entirely `safe` Rust -- no `unsafe` keyword anywhere
near the crash site -- and the behavior is inconsistent: it might only
happen in `--release` builds, only under specific optimization levels, only
after enough iterations for the allocator to reuse memory in a particular
way, or not at all under a debugger. This is the signature of undefined
behavior triggered by an `unsafe` block elsewhere that violated one of
Rust's invariants; because UB is not "an error at the violation site," the
actual observable failure can appear anywhere the compiler's optimizer
happened to make an invalid assumption based on the broken invariant.

## Likely causes
1. **Aliasing violation** -- an `unsafe` block created two mutable
   references (or a mutable and a shared reference) to the same memory at
   the same time, often via raw pointer casts (`&mut *(ptr as *mut T)`) or
   `std::mem::transmute`. The optimizer is allowed to assume `&mut T` is
   never aliased and can reorder or cache reads/writes based on that
   assumption, producing corruption that only appears after optimization.
2. **Reading uninitialized memory as if it were initialized** -- e.g. using
   `MaybeUninit::uninit().assume_init()` before every field is actually
   written, or over-eager use of `mem::zeroed()` for a type that isn't
   valid when all-zero (references, `bool`, enums with niches). The bit
   pattern often "looks" plausible by accident in debug builds and only
   breaks once the optimizer relies on the type's validity invariant.
3. **An out-of-bounds or misaligned raw pointer access** via
   `slice::get_unchecked`, manual pointer arithmetic, or an FFI boundary
   where a length/pointer pair was constructed incorrectly -- this can
   silently read adjacent heap memory instead of crashing immediately,
   so the corruption surfaces later when that memory is reused for
   something else.
4. **A `Send`/`Sync` unsafe impl was added to silence a compiler error**
   without actually verifying the type is safe to share/move across
   threads -- e.g. implementing `unsafe impl Sync for Wrapper<*mut T> {}`
   to get code compiling, which then allows genuine data races on the raw
   pointer that the type system was correctly trying to prevent.

## Diagnose
- Run the test/reproduction under **Miri** (`cargo +nightly miri test` or
  `cargo +nightly miri run`) -- Miri directly detects most aliasing
  violations, uninitialized-memory reads, out-of-bounds access, and invalid
  bit patterns at the exact `unsafe` operation that caused them, rather than
  wherever the corruption later surfaces. This is the single most effective
  tool for this class of bug and should be the first thing reached for.
- If Miri can't run (e.g. the crash needs real OS/FFI interaction it doesn't
  support), build with AddressSanitizer: `RUSTFLAGS="-Z sanitizer=address"
  cargo +nightly run` (or `-Z sanitizer=memory` for uninitialized reads) to
  get a precise fault location instead of a downstream symptom.
- Grep the crate for every `unsafe` block and specifically check: any
  `transmute`, any `assume_init`, any raw pointer dereference, and any
  manual `unsafe impl Send`/`unsafe impl Sync`. Each of these is a place
  where the compiler's guarantees were manually asserted rather than
  verified -- audit each one's safety comment (or add one if missing) and
  confirm the invariant it claims is actually upheld by every caller.
- Compare debug vs. release behavior: if the bug only appears in
  `--release`, that's a strong signal it's UB the optimizer is exploiting
  (debug builds often happen to leave memory in a state that masks the
  violation), not an ordinary logic bug.

## Fix
Narrow every `unsafe` block to the smallest possible scope and attach an
explicit `// SAFETY:` comment stating the invariant it depends on and why
that invariant holds at this call site -- this makes violations reviewable
and is standard practice in the Rust ecosystem specifically because `unsafe`
correctness can't be checked by the compiler:
```rust
// SAFETY: `ptr` was obtained from `Box::into_raw` immediately above and
// has not been aliased or freed; `len` matches the original allocation.
let slice = unsafe { std::slice::from_raw_parts(ptr, len) };
```
For aliasing violations, restructure to avoid ever having two live mutable
references to the same memory -- use split-borrow helpers (`split_at_mut`),
indices instead of pointers, or `Cell`/`UnsafeCell` explicitly where
interior mutability is genuinely needed, rather than raw pointer casts that
bypass the aliasing model entirely. For uninitialized-memory cases, build
the value field-by-field with `MaybeUninit::write` for each field and only
call `assume_init()` once every field is proven written (or use a safe
builder abstraction that tracks this). For FFI pointer/length pairs,
validate the length against the actual allocation size before constructing
any Rust reference or slice from it, and centralize that validation in one
audited helper rather than repeating raw conversions at each call site.

## Pitfalls
- Adding `unsafe` to fix a borrow-checker error as a shortcut, without an
  actual invariant to uphold -- if you can't write the `// SAFETY:` comment
  because there's no real reason the operation is sound, the fix is to
  restructure the safe code, not to force it through `unsafe`.
- Trusting that "it works in my tests" means the `unsafe` block is correct
  -- UB is often silent until a different allocator, optimization level, or
  input triggers the specific miscompilation; passing tests are not
  evidence of soundness for `unsafe` code the way they are for safe code.
- Wrapping unsound `unsafe` code in a safe-looking public API without
  actually verifying every caller upholds the invariant -- once the
  `unsafe` is hidden behind a safe function signature, callers have no way
  to know they must maintain a precondition the type system doesn't
  enforce, and violations become even harder to trace back.

## Verify
Run the full test suite (and ideally the specific reproduction case) under
`cargo +nightly miri test` and confirm zero UB diagnostics, not just that
the test passes -- a test can pass while Miri still flags real UB that
hasn't manifested as an observable failure yet. Re-run in both debug and
`--release` profiles to confirm the fix isn't merely hiding the issue in one
optimization level. For any `unsafe` block touched, confirm it now has a
`// SAFETY:` comment reviewed by someone other than the author, since
self-review of safety invariants is the weakest point in this class of bug.
