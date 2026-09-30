---
name: question-mark-operator-error-type-conversion-mismatch
description: Fix a compile error from the ? operator because the propagated error type does not implement From for the function's declared error type.
triggers: ["the trait From<...> is not implemented for", "question mark operator error conversion", "error trait not satisfied cannot use question mark", "mismatched error types with ? propagation", "how to convert error types in rust"]
permissions: ["READ"]
---

## Symptom
A function using `?` to propagate an error from a called function (a
library call, a parse, an I/O operation) fails to compile with something
like `` the trait `From<std::num::ParseIntError>` is not implemented for
`MyError` `` or `` `?` couldn't convert the error to `Box<dyn
std::error::Error>` ``. The calling code often mixes several different
fallible operations (file I/O, parsing, a custom domain error) inside one
function that declares a single `Result<T, E>` return type, and `?` needs
every one of those distinct error types to be convertible into that single
`E` via `From`, which usually isn't true out of the box the moment more
than one error-producing library is involved.

## Likely causes
1. **The function's error type is a custom enum/struct that hasn't
   implemented `From<SourceError>` for one of the error types actually
   produced inside the function body** -- `?` desugars to calling
   `From::from(err)` on the underlying error, so it's a hard compile error
   (not a warning) if that conversion doesn't exist for a specific source
   type.
2. **The function mixes multiple distinct fallible dependencies** (e.g.
   `std::io::Error` from a file read and `serde_json::Error` from parsing)
   under one `Result<T, MyError>` return type, and only one of the two has a
   `From` impl written so far -- this typically shows up incrementally, as
   a new failure-prone call is added to a function that already compiled.
3. **A generic/boxed error type was used inconsistently** -- some functions
   return `Result<T, Box<dyn Error>>` and others return a specific concrete
   error enum, and `?` can't silently convert between two different
   abstraction levels of "an error" without an explicit `From` bridging
   them (or a shared trait object boundary).
4. **A third-party library's error type doesn't implement
   `std::error::Error`** (or doesn't implement `Send + Sync + 'static`,
   which many error-boxing patterns require), so even generic "catch-all"
   approaches like `Box<dyn Error>` or the `anyhow`/`eyre` crates fail to
   accept it without an adapter.

## Diagnose
- Read the exact error: it names both the source error type and the target
  `E` the function declares -- confirm which specific call site produces
  the unconvertible error by checking which fallible call in the function
  body returns that source type.
- Check the custom error enum/struct for existing `From` impls (often
  hand-written or via `#[derive(thiserror::Error)]` with `#[from]`
  attributes) -- count how many of the function's actual fallible
  dependencies have a corresponding variant/impl versus how many don't.
- If using `anyhow`/`eyre` and still hitting this, check whether the
  source error type actually implements `std::error::Error + Send + Sync +
  'static` -- some hand-rolled error types (or ones wrapping non-'static
  data like a borrowed `&str`) don't, and no amount of `?` chaining fixes
  that without wrapping the message manually.
- Grep the crate for how many distinct concrete error types cross function
  boundaries that use `?` -- if it's more than a handful and each needs
  hand-written `From` impls, that's a signal to consolidate on one error
  strategy (typed enum with `thiserror`, or `anyhow` for application code)
  rather than writing ad hoc conversions per call site.

## Fix
For library crates (where callers need to match on specific error kinds),
define one error enum per module/crate and derive the `From` conversions
with `thiserror` so each variant's boilerplate is generated, not
hand-maintained:
```rust
#[derive(thiserror::Error, Debug)]
enum ConfigError {
    #[error("failed to read config file")]
    Io(#[from] std::io::Error),
    #[error("failed to parse config")]
    Parse(#[from] serde_json::Error),
}

fn load_config(path: &str) -> Result<Config, ConfigError> {
    let text = std::fs::read_to_string(path)?; // io::Error -> ConfigError::Io via #[from]
    let config = serde_json::from_str(&text)?; // serde_json::Error -> ConfigError::Parse
    Ok(config)
}
```
For application/binary code where callers don't need to match on specific
error variants (just report/log them), use `anyhow::Result<T>` (or `eyre`)
and let its blanket `From` impl over `std::error::Error + Send + Sync +
'static` handle the conversion automatically, adding context with
`.context("...")` at each call site instead of writing per-source-type
`From` impls at all. Don't mix strategies within one crate -- pick typed
errors for library boundaries and `anyhow`-style errors for application
code, and convert at the seam between them explicitly.

## Pitfalls
- Reaching for `.unwrap()` or `.expect()` at the failing `?` call site just
  to make the compiler stop complaining -- this converts a recoverable
  error into an unconditional panic, discarding the whole point of the
  `Result` propagation the code was trying to do.
- Writing a hand-rolled `From` impl that discards the original error's
  detail (e.g. converting to a bare `String` with `.to_string()` and losing
  the structured source), which then breaks `std::error::Error::source()`
  chaining and makes root-causing production errors harder later.
- Using `anyhow::Error` as a library's public return type -- it erases the
  concrete error type, so callers outside the crate can't `match` on
  specific failure kinds to handle them differently (e.g. retry on a
  network error but not on a validation error), which is fine for
  application code but a real API regression for a library.

## Verify
Run `cargo build` and confirm the specific `From<...>` trait error is
resolved for every fallible call in the function, then check
`cargo clippy` for any `?`-related lints (e.g. unnecessary `.map_err`) left
over from a partial fix. Write a test that deliberately triggers each
distinct underlying error (bad path for the I/O error, malformed input for
the parse error) and asserts the resulting error matches the expected
variant (for typed errors) or contains the expected context string (for
`anyhow`), confirming the conversion preserves useful information rather
than just compiling.
