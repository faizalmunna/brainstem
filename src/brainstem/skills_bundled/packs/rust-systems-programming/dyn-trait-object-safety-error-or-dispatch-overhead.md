---
name: dyn-trait-object-safety-error-or-dispatch-overhead
description: Resolve a "the trait cannot be made into an object" compile error or unexpected performance overhead from reaching for dyn Trait where a generic would work.
triggers: ["the trait cannot be made into an object", "doesnt satisfy Sized error with dyn", "dyn Trait slower than generic benchmark", "method has generic type parameters trait object", "cannot be made into an object because it uses generic"]
permissions: ["READ"]
---

## Symptom
Either of two related situations: (1) code using `Box<dyn Trait>` or `&dyn
Trait` fails to compile with `the trait \`Foo\` cannot be made into an
object` (or `\`Foo\` doesn't satisfy Sized`, or "method references the
\`Self\` type in its return"), even though the trait works fine when used
generically; or (2) the code compiles and runs correctly using `dyn Trait`,
but a profiler or benchmark shows meaningfully worse performance than an
equivalent generic (`impl Trait`/`<T: Trait>`) version, in a hot loop where
the extra virtual-call indirection and lost inlining actually matter.

## Likely causes
1. **The trait has a method that returns `Self` or takes `Self` by value**
   -- e.g. `fn clone_boxed(&self) -> Self` -- which is fundamentally
   incompatible with dynamic dispatch because the concrete size of `Self`
   isn't known through a `dyn` pointer; the vtable has no way to represent
   "return a value of whatever concrete type this trait object actually is."
2. **The trait has a generic method** (`fn process<T: Display>(&self, x: T)`)
   -- a vtable needs one fixed function pointer per method, but a generic
   method needs a different monomorphized instantiation per `T`, which is
   unbounded and can't be enumerated into a single vtable entry.
3. **`dyn Trait` was chosen reflexively for a case with a small, closed set
   of implementors known at compile time** (e.g. an internal enum-like set
   of strategies), where an enum with a `match`, or a generic function
   parameterized over the trait, would let the compiler monomorphize and
   inline each call, avoiding both the vtable indirection and the heap
   allocation that `Box<dyn Trait>` usually implies.
4. **A hot loop calls a `dyn Trait` method per-iteration** where the
   concrete type is actually the same on every call within that loop
   (just not known at the call site's compile time) -- each call pays a
   vtable lookup and forgoes inlining/auto-vectorization that a
   monomorphized generic would get from LLVM.

## Diagnose
- For the object-safety compile error, read the exact rule cited (`rustc
  --explain E0038`) -- it will name the specific offending method (`Self`
  return, generic parameters, or an associated const). Check whether that
  method is actually called through the trait object anywhere, or only
  through concrete types -- if it's never called dynamically, it can often
  be excluded from the object-safe portion via `where Self: Sized` on just
  that method, which removes it from the vtable requirement while keeping
  it callable on concrete types.
- For the performance question, don't guess -- benchmark both versions with
  `cargo bench` (criterion) on the actual call pattern, and check whether
  the hot path even has enough call volume for vtable indirection to matter;
  for most application code (not called millions of times per second) the
  difference is noise, and converting to generics is not worth the
  code-size/compile-time tradeoff unless a profiler shows the indirection
  actually dominates.
- If performance does matter, profile with `perf record`/`perf report` (or
  `cargo flamegraph`) and check whether the `dyn Trait` call site shows up
  as a meaningful fraction of samples, versus the work the method actually
  does -- indirection overhead is only worth removing if it's a measurable
  fraction of total time, not simply "present."
- Count actual implementors of the trait in the codebase: if it's a fixed,
  small set that doesn't need to grow via external plugins, that's a signal
  an enum or generic is a better fit than `dyn Trait`'s open-set
  flexibility, which you're paying for without using.

## Fix
For the object-safety error, either remove the offending method from the
trait's object-safe surface with `where Self: Sized`:
```rust
trait Shape {
    fn area(&self) -> f64; // dyn-compatible
    fn clone_boxed(&self) -> Box<dyn Shape> where Self: Sized + Clone {
        Box::new(self.clone())
    } // excluded from vtable, still callable on concrete T: Shape + Clone
}
```
or split the trait into a dyn-safe core and a separate generic-only
extension trait, or switch the call site from `dyn Trait` to a generic
bound (`fn process<T: Trait>(x: T)` / `impl Trait` argument) if dynamic
dispatch was never actually required (no heterogeneous collection of
different concrete types needed at runtime).

For the performance case, when the actual set of implementors is closed and
known, prefer an enum with a `match`-dispatched method over `dyn Trait` --
this gives the compiler full visibility to inline and optimize per-variant:
```rust
enum Strategy { Fast(FastImpl), Accurate(AccurateImpl) }
impl Strategy {
    fn run(&self, input: &Data) -> Output {
        match self { Strategy::Fast(s) => s.run(input), Strategy::Accurate(s) => s.run(input) }
    }
}
```
When the set is genuinely open (plugins, user-supplied implementations) and
heterogeneity at runtime is required, `dyn Trait` is the correct tool --
don't fight it; instead ensure the hot inner work (not the dispatch itself)
is where the time goes, e.g. by batching calls to amortize the vtable hop.

## Pitfalls
- Converting an entire codebase from `dyn Trait` to generics for
  "performance" without profiling first -- this often increases compile
  times and binary size (one monomorphized copy per concrete type) for a
  runtime win that never mattered in that code path, which is a worse
  tradeoff than the indirection it replaced.
- Using `where Self: Sized` to paper over an object-safety error without
  checking whether that method is actually needed dynamically -- if it is,
  this silently makes it uncallable through the trait object and the
  failure moves from a compile error to a missing-functionality bug
  discovered later.
- Mixing `Box<dyn Trait>` in a hot loop with allocation on every call (e.g.
  constructing a new boxed trait object per iteration instead of reusing
  one) -- the allocation, not the vtable dispatch, is often the actual
  performance cost, and switching to generics alone won't fix that if the
  allocation pattern stays the same.

## Verify
For the compile-error fix, run `cargo build` and confirm `E0038` is gone,
then add a test that actually stores heterogeneous implementors in a
`Vec<Box<dyn Trait>>` (or equivalent) and calls the trait's dyn-safe methods
through it, to confirm the object-safe surface still does what's needed.
For the performance fix, re-run the same `cargo bench`/`flamegraph`
comparison used to diagnose it and confirm a measured improvement (not just
an assumed one) before keeping the generic version, since the added
code-size/compile-time cost should be justified by an actual number.
