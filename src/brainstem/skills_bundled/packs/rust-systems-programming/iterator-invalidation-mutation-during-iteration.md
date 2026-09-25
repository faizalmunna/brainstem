---
name: iterator-invalidation-mutation-during-iteration
description: Fix a borrow checker rejection or logic bug caused by trying to mutate a collection while iterating over it with a live iterator.
triggers: ["cannot borrow as mutable while borrowed error in a for loop", "modifying a vec while iterating rust", "retain vs manual loop deletion", "index out of bounds after removing during iteration", "cannot borrow immutable because also borrowed as mutable in loop"]
permissions: ["READ"]
---

## Symptom
A `for` loop iterating over a `Vec`/`HashMap`/other collection, where the
body also tries to insert into, remove from, or otherwise mutate that same
collection, either fails to compile with a borrow-checker error (`cannot
borrow \`v\` as mutable because it is also borrowed as immutable`) or -- if
written with indices to dodge the borrow checker -- compiles but panics
with an index-out-of-bounds or produces silently wrong results (skipped
elements, elements visited twice) because removing an element during
iteration shifts every subsequent index.

## Likely causes
1. **A `for item in &collection` loop's body calls a mutating method on the
   same `collection`** (`.push()`, `.remove()`, `.insert()`) -- the `for`
   loop holds a live shared borrow (via the iterator) for its entire
   duration, so the borrow checker correctly rejects any mutable borrow
   attempted inside it; this is the compile-time version of the bug.
2. **The developer switches to index-based iteration
   (`for i in 0..v.len() { if cond { v.remove(i); } }`) specifically to
   dodge the borrow checker error**, which compiles, but `Vec::remove`
   shifts every following element left by one -- the loop's `i` no longer
   lines up with the collection after a removal, silently skipping the
   element that shifted into the just-removed slot, or panicking with an
   out-of-bounds index once `v.len()` has shrunk past what the fixed
   `0..original_len` range assumed.
3. **A `HashMap`/`HashSet` is iterated with `.iter()` while the body tries
   to `.insert()` a new key** -- beyond the borrow conflict, inserting
   during iteration over a hash-based collection is additionally unsound
   because insertion can trigger a resize/rehash, invalidating the
   iterator's internal bucket position entirely; Rust's borrow checker
   prevents this at compile time, but the underlying reason is deeper than
   just "two borrows conflict."
4. **Code wants to build a *new* filtered/transformed collection but
   mutates the original in place instead**, out of habit from languages
   where in-place filtering during iteration is common (with its own
   well-known pitfalls there too) -- this is often simply the wrong
   approach for the actual goal (produce a filtered result) rather than a
   borrow-checker problem to solve at all.

## Diagnose
- Read what the loop body is actually trying to accomplish: removing
  elements matching a condition, transforming elements in place, or
  collecting a derived result. Each has a different correct idiom in Rust,
  so identify which one before picking a fix.
- If already using index-based iteration to dodge a borrow error, check
  whether indices are computed once (`0..v.len()`) before any removal --
  this is the concrete tell that the code has the index-drift bug (case 2),
  since a correct index-based removal loop has to account for the shift
  explicitly (e.g. iterate in reverse, or not increment the index after a
  removal).
- For the `HashMap` insert-during-iterate case, check whether the intent is
  actually "add entries based on existing entries" -- if so, that
  fundamentally requires collecting the new entries into a separate
  structure first, not a syntax tweak to the existing loop.
- Run the index-based version under `cargo test` with a case that removes
  more than one adjacent element and check the resulting collection
  contents against the expected output by hand -- this is the fastest way
  to surface silently-wrong results from index drift, since it often
  doesn't panic on small inputs.

## Fix
For removing elements matching a predicate, use the standard library's
purpose-built retaining methods instead of a manual loop -- they handle the
index-shifting correctly internally:
```rust
v.retain(|x| !should_remove(x)); // keeps elements where the closure returns true
```
For transforming elements in place, mutate through `.iter_mut()`, which the
borrow checker permits because it hands out one mutable borrow per element
without needing to also mutate the collection's structure (length):
```rust
for item in v.iter_mut() { item.value *= 2; }
```
For building a new collection derived from an existing one (the common
actual intent behind "modify while iterating"), iterate an immutable borrow
and collect into a new structure rather than mutating in place:
```rust
let filtered: Vec<_> = v.iter().filter(|x| keep(x)).cloned().collect();
```
For the `HashMap` insert-during-iterate case, collect the new entries into a
separate `Vec`/`HashMap` while iterating with a shared borrow, then extend
the original after the iteration borrow ends:
```rust
let additions: Vec<_> = map.iter().filter_map(|(k, v)| derive_new_entry(k, v)).collect();
map.extend(additions);
```

## Pitfalls
- Reaching for `.clone()` on the whole collection just to get an iterable
  copy to loop over while mutating the original -- this works but is
  wasteful for large collections when `retain`/`iter_mut`/collect-then-extend
  solve the same problem without a full copy; reserve cloning for cases
  where the elements are genuinely needed independently afterward.
- Using `while let Some(item) = v.pop() { ... }` as a generic "iterate and
  mutate" replacement when order matters -- `pop` iterates in reverse
  (from the end), which silently changes processing order compared to the
  original forward iteration and can break logic that assumed first-to-last
  processing.
- Assuming `retain`'s closure can have side effects that depend on
  iteration order across elements (e.g. a running total used to decide
  keep/remove) without checking the documented iteration order guarantee
  for the collection type -- for `Vec` it's guaranteed front-to-back, but
  relying on this for a `HashMap`'s `retain` is not safe since hash-based
  collections don't guarantee a stable iteration order.

## Verify
For a `retain`-based fix, write a test with a collection containing
multiple adjacent elements that should be removed together and assert the
final contents exactly match the expected remaining elements, specifically
covering the case that would have exposed index drift in a manual loop
(e.g. removing elements at consecutive indices). For an `iter_mut()`
transform, assert both the length is unchanged and every element reflects
the transformation. For the collect-then-extend pattern, assert the
original collection's pre-existing entries are untouched and only the newly
derived entries were added.
