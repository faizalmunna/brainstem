---
name: cargo-resolver-pulls-old-incompatible-transitive-dependency
description: Fix a build failure or subtle bug caused by cargo's dependency resolver locking in an old or incompatible transitive version of a shared crate.
triggers: ["duplicate crate versions in dependency tree", "cargo update wont bump a transitive dependency", "trait not implemented because of version mismatch", "multiple versions of the same crate compiled in", "Cargo.lock has an old version pinned"]
permissions: ["READ"]
---

## Symptom
The build fails with a confusing type mismatch where two types that look
identical (same name, same crate) are reported as different -- e.g. `` expected
struct `bytes::Bytes`, found struct `bytes::Bytes` `` -- or a runtime
behavior difference shows up that traces back to a dependency the
developer never directly pinned. Alternatively, `cargo update` or adding a
new dependency doesn't bump a transitive crate to the version a `Cargo.toml`
range should technically allow, and `cargo tree -d` shows the same crate
appearing at two different versions. This happens because Cargo resolves
one version per crate *per major-version-incompatible line*, and different
parts of the dependency graph can end up requiring incompatible major
versions of the same underlying crate, or the resolver can pick an older
minimum-compatible version than expected.

## Likely causes
1. **Two direct or transitive dependencies require incompatible major
   versions of the same crate** (e.g. one depends on `rand 0.8` and another
   on `rand 0.9`) -- Cargo compiles both as genuinely separate crates in the
   dependency graph (SemVer-incompatible versions are never unified), so
   any code trying to pass a value of one version's type where the other is
   expected fails to type-check even though the crate name and the type's
   name are identical.
2. **`Cargo.lock` has an old version checked in and committed**, and nobody
   has run `cargo update` since a dependency's `Cargo.toml` range was
   widened -- Cargo respects the lockfile by default (that's its whole
   purpose, reproducible builds), so a stale lockfile silently keeps
   building against an old, possibly-patched-since version until someone
   explicitly updates it.
3. **A dependency's `Cargo.toml` uses an overly loose version requirement**
   (e.g. a caret range that's wider than actually tested) and the resolver
   picks the *minimum* version satisfying all constraints in the graph,
   which can be older than what any individual developer has locally,
   especially right after a fresh `cargo update` picks a "lowest that still
   satisfies everyone" solution rather than "latest of everything."
4. **A workspace with multiple crates has inconsistent version requirements
   for a shared internal or external dependency across member `Cargo.toml`
   files**, and the resolver's per-workspace unification behaves
   differently than each crate's author assumed when they wrote their own
   version range in isolation.

## Diagnose
- Run `cargo tree -d` (duplicates) to list every crate that appears more
  than once in the resolved graph, with each version and the dependency
  path that pulled each one in -- this directly names the conflicting
  requirers without needing to manually trace `Cargo.toml` files.
- For a type-mismatch error citing what looks like the same type twice, run
  `cargo tree -i <crate-name>` (invert) on the crate named in the error to
  see every path that depends on it and at which version -- this shows
  exactly which two parts of the graph disagree.
- Check whether `Cargo.lock` is committed and how old it is relative to
  when the affected dependency last published a compatible release
  (`cargo search <crate>` or the crate's crates.io page) -- a lockfile
  untouched for months on a fast-moving dependency is a common source of
  "why is this still on an old version."
- For workspaces, diff the version requirement for the shared dependency
  across every member `Cargo.toml` (`grep -r "^dependency-name" */Cargo.toml`)
  to spot inconsistent ranges before assuming the resolver is at fault.

## Fix
For genuinely incompatible major-version requirements from two different
dependencies, the real fix is usually upgrading (or in rare cases
downgrading) one of the direct dependencies to align both on the same major
version of the shared crate -- check whether a newer release of the
outdated direct dependency exists that itself depends on the newer shared
crate version, and bump to it:
```toml
# If crate-a still requires rand 0.8 but crate-b needs rand 0.9,
# check crate-a's changelog/crates.io page for a version that's
# been updated to depend on rand 0.9, and bump to that instead
# of trying to force a shared version cargo can't unify.
```
When no aligned version exists yet, isolate the incompatibility behind a
small conversion function at the boundary between the two dependencies
(converting explicitly between the two versions' types) rather than trying
to force unification that the ecosystem hasn't caught up to yet.

For a stale lockfile, run `cargo update -p <crate>` to bump just the
affected dependency (safer than a blanket `cargo update`, which can move
many dependencies at once and widen the blast radius of a single fix), then
re-run the full test suite before committing the updated `Cargo.lock`.

For overly loose ranges pulling in an older-than-expected minimum version,
tighten the direct dependency's version requirement in `Cargo.toml` to a
minimum you've actually tested against (`crate = ">=1.4, <2"` instead of a
bare caret that happens to resolve low), and consider running
`cargo update -Z minimal-versions` (nightly) periodically in CI to catch
cases where the code accidentally relies on features/fixes only present in
a newer-than-declared minimum version.

## Pitfalls
- Running a blanket `cargo update` to fix one specific stale dependency --
  this can silently bump many unrelated dependencies at once, some of which
  may introduce their own breaking behavior changes, making it hard to
  isolate what actually caused a subsequent regression.
- Pinning a dependency to an exact version (`=1.2.3`) to "stop this from
  happening again" -- this prevents cargo from ever picking up patch-level
  security or bug fixes automatically and just relocates the staleness
  problem to "someone has to remember to manually bump this," which is
  usually worse than a well-maintained range.
- Assuming duplicate versions shown by `cargo tree -d` are always a problem
  to fix immediately -- some duplication (especially for small, cheaply
  compiled crates) is a normal, harmless consequence of a large dependency
  graph; prioritize fixing duplicates that are large (compile time/binary
  size) or that actually cause a type-mismatch compile error, not every
  entry in the list.

## Verify
Run `cargo tree -d` again after the fix and confirm the specific crate
that was duplicated now resolves to a single version (or, if some
duplication is unavoidable and harmless, confirm it's no longer the pair
that caused the original type-mismatch error). Run the full test suite
against the updated `Cargo.lock` and confirm it passes, then check
`cargo build --timings` or `cargo bloat` before/after if the duplication
was large, to confirm compile time or binary size actually improved rather
than just the symptom error disappearing.
