---
name: monomorphization-macro-bloat-slow-compile
description: Diagnose a Rust crate whose build time has become very slow due to excessive generic monomorphization or heavy declarative or procedural macro expansion.
triggers: ["cargo build takes forever", "compile times keep getting worse", "incremental build still slow rust", "why is my rust binary so large", "cargo build --timings shows one crate dominating"]
permissions: ["READ"]
---

## Symptom
`cargo build` (especially a clean or `--release` build) takes minutes where
it used to take seconds, and the slowdown crept in gradually rather than
appearing after one obvious change. Developers notice it most as
increasingly painful edit-compile-test loops. It's often blamed on "Rust is
just slow to compile" in general, which obscures that specific, findable
causes in the codebase -- not an inherent language property -- are usually
responsible and are fixable without abandoning the patterns that caused
them.

## Likely causes
1. **Heavy use of generic functions/types instantiated over many different
   concrete type parameters** -- each distinct `T` the compiler sees a
   generic function called with gets its own fully-compiled copy
   (monomorphization); a generic-heavy library called with dozens of
   different types across the codebase can silently multiply the actual
   amount of code LLVM has to compile many times over.
2. **A procedural macro (derive or attribute) that generates a large amount
   of code per invocation** -- e.g. a serialization derive applied to
   hundreds of large structs, or an ORM/schema macro that expands into
   substantial boilerplate -- proc macros run their own compilation step
   (they're compiled and executed at build time) and their expanded output
   still has to be type-checked and compiled like any other code, so both
   the macro's own build and its expansion size contribute.
3. **A declarative (`macro_rules!`) macro used recursively or with many
   invocation sites generating repetitive code** that could instead be a
   single generic function or a runtime loop -- macros trade a small
   authoring convenience for compiling out N copies of similar code instead
   of one shared implementation.
4. **Too few codegen units combined with LTO enabled for a large crate**,
   or the whole workspace compiling as very few crates instead of being
   split -- Rust's incremental and parallel compilation works at the
   crate/codegen-unit level, so one giant crate serializes work that could
   otherwise be parallelized across cores or skipped entirely by
   incremental compilation when unrelated files change.

## Diagnose
- Run `cargo build --timings` (stable since a while back) and open the
  generated HTML report -- it shows per-crate compile time and
  parallelism, immediately surfacing which single crate or dependency
  dominates total wall-clock time.
- For monomorphization specifically, check binary size and symbol count:
  `cargo bloat --release --crates` shows which crates contribute the most
  compiled code size, and a generic-heavy crate showing up disproportionately
  large relative to its source size is a strong signal of monomorphization
  bloat.
- For macro suspicion, run `cargo expand` on the specific module using the
  macro and visually compare the expanded output size to the original
  source -- a derive or `macro_rules!` invocation expanding into hundreds
  of lines per call site, multiplied by many call sites, quantifies the
  actual cost rather than just suspecting it.
- Check `Cargo.toml` for `[profile.release] lto = true` combined with
  `codegen-units = 1` -- both are legitimate for shipping a final optimized
  binary but are expensive; confirm whether they're also applied to
  everyday dev builds (they shouldn't be -- dev profile should stay fast).

## Fix
For monomorphization bloat, convert the hot generic surface to use dynamic
dispatch (`&dyn Trait`) or move the type-independent logic into a
non-generic inner function that the generic wrapper delegates to, so only a
thin generic shim gets duplicated per type instead of the whole
implementation:
```rust
// Before: full body monomorphized once per T.
fn process<T: Serialize>(items: &[T]) -> String { /* large body */ }

// After: only the thin generic shim is duplicated; the real work compiles once.
fn process<T: Serialize>(items: &[T]) -> String {
    let values: Vec<serde_json::Value> = items.iter().map(|i| serde_json::to_value(i).unwrap()).collect();
    process_values(&values)
}
fn process_values(values: &[serde_json::Value]) -> String { /* large body, compiled once */ }
```
For macro bloat, replace repetitive `macro_rules!`-generated code with a
genuinely shared function or a const-generic/generic implementation where
possible, and audit whether every derive is actually needed on every type
(e.g. deriving `Serialize`/`Deserialize` on internal-only types that are
never serialized). For build configuration, keep `codegen-units` at its
default (parallel) for dev builds and only tighten it (`lto = "thin"` or
`"fat"`, `codegen-units = 1`) in the `[profile.release]` used for actual
release artifacts, not the default profile developers iterate against.
Split a monolithic crate into multiple crates along natural boundaries so
cargo can compile and cache them independently and in parallel.

## Pitfalls
- Reaching for `dyn Trait` everywhere reflexively to "fix compile times"
  without checking whether monomorphization was actually the dominant cost
  via `--timings`/`cargo bloat` first -- this trades compile time for
  runtime dispatch overhead in code paths where compile time was never
  actually the bottleneck, per the dyn-vs-generic tradeoff.
- Splitting a crate into many tiny crates purely for parallelism without
  regard to actual module boundaries -- excessive crate-splitting adds
  cross-crate API friction (more `pub`, more version/visibility management)
  and can make workspace-wide refactors slower to reason about even if raw
  build parallelism improves.
- Adding `lto = true` and `codegen-units = 1` to the `dev` profile because
  "it made release faster" -- this makes every local `cargo build` pay
  release-grade optimization cost, which is the opposite of what a fast
  local edit loop needs.

## Verify
Re-run `cargo build --timings` after the change and compare total wall-clock
time and the specific crate's share of it against the baseline captured
before the fix -- confirm a measured reduction, not just a subjective "feels
faster." For monomorphization fixes, re-run `cargo bloat --release --crates`
and confirm the affected crate's contributed size dropped. Time a clean
build (`cargo clean && cargo build`) and an incremental build (touch one
file, rebuild) separately, since the two fixes (monomorphization vs. crate
splitting/codegen-units) affect each differently.
