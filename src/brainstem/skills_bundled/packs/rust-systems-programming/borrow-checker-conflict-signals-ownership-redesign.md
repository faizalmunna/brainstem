---
name: borrow-checker-conflict-signals-ownership-redesign
description: Recognize when a mutable-and-immutable-borrow conflict the compiler rejects is really a sign the data structure's ownership model is wrong, not a bug to clone away.
triggers: ["cannot borrow as mutable because it is also borrowed as immutable", "cannot borrow x as mutable more than once at a time", "fighting the borrow checker", "second mutable borrow occurs here", "borrow checker wont let me update while iterating"]
permissions: ["READ"]
---

## Symptom
Code that looks like an ordinary update-while-reading operation --
iterating over a collection and mutating another field, or mutating an item
found via a lookup while also holding a reference used for the lookup --
fails with `cannot borrow \`self\` as mutable because it is also borrowed as
immutable` or `cannot borrow \`x\` as mutable more than once at a time`. The
first instinct is usually to sprinkle `.clone()` calls or wrap fields in
`RefCell` until it compiles, but the conflict often keeps reappearing in
new spots as the code grows, which is the tell that the borrow checker is
correctly reporting a real aliasing problem in the design, not a false
positive.

## Likely causes
1. **A single struct holds both the "index"/lookup data and the "payload"
   data being mutated**, so any operation that looks something up and then
   mutates based on what it found necessarily borrows the same `self` twice
   with incompatible mutability -- this is a sign the two concerns (index,
   data) should be separate structures, not aliased through one `&mut self`.
2. **Iterating over a collection while mutating a different part of the same
   owning struct** (e.g. `for item in &self.items { self.total += item.cost }`)
   -- the shared borrow from the iterator and the mutable borrow of `self`
   overlap even though the fields don't actually alias in memory, because the
   borrow checker (pre-Polonius) borrows at the struct-field level in ways
   that don't always see through method boundaries.
3. **A graph-like or back-referencing structure** (parent points to child,
   child needs to reference parent, or a linked list with mutation) is being
   modeled with plain references, which cannot express "these two things
   sometimes need to be mutated independently despite conceptually pointing
   at each other" -- this is fundamentally not expressible with `&`/`&mut`
   without indices, arenas, or interior mutability.
4. **A closure captures `self` (or a field) by mutable reference while
   another part of the same expression still needs a shared reference to
   it** -- common with callback-registration patterns where the callback
   closure and the caller both want access to the same owner.

## Diagnose
- Read the two borrow spans in the error message carefully: is the second
  borrow *actually* touching the same memory as the first, or only the same
  *struct* while touching different fields? If it's genuinely disjoint
  fields, try splitting the borrow explicitly (`let Struct { field_a, field_b,
  .. } = self;`) or extracting a method that takes `&mut self.field_a`
  directly -- this resolves pure field-disjointness false-conflicts without
  any redesign.
- If the borrows really do touch the same data (a lookup result and a
  mutation target derived from it), sketch the data flow: is there a natural
  seam where "find the thing" and "mutate the thing" could be two owned
  entities instead of one entity referencing itself? That's the redesign
  signal.
- Count how many places in the codebase already have a `.clone()` or
  `RefCell` inserted to route around a borrow conflict on the same struct.
  Two or more independent workarounds on the same type is a strong signal
  the type's shape is wrong, not that each site has an unrelated one-off
  problem.
- Ask whether the relationship being modeled is inherently graph-shaped
  (nodes referencing each other, possibly cyclically). If yes, `&`/`&mut`
  references are the wrong tool regardless of how carefully borrows are
  scoped -- move to indices or an arena immediately rather than continuing
  to fight it.

## Fix
Treat the conflict as a design smell first: split the struct so the piece
being read and the piece being mutated are separately borrowable. A common
pattern is splitting one "god struct" into a lookup/index component and a
data component that's passed alongside it:
```rust
// Before: one struct, every read-then-mutate op double-borrows self.
struct Inventory { index: HashMap<String, usize>, items: Vec<Item> }

// After: caller looks up the index (immutable borrow ends), then
// mutates items directly -- no overlapping borrow of one `self`.
fn restock(index: &HashMap<String, usize>, items: &mut [Item], name: &str, qty: u32) {
    if let Some(&i) = index.get(name) {
        items[i].qty += qty;
    }
}
```
For graph/back-reference shapes, switch representation entirely: store
`Vec<Node>` and reference nodes by `usize` index (or use a slotmap/arena
crate) instead of storing references or `Rc` pointers between nodes. Indices
are `Copy`, don't borrow anything, and sidestep the whole category of
conflict because "mutate node A while looking at node B" becomes two
independent indexing operations into one `Vec`, not two borrows of related
objects.

For field-disjointness false-conflicts (case 2), prefer destructuring the
struct to borrow fields independently, or split the method so each half
only takes the field it needs, rather than reaching for `RefCell`.

## Pitfalls
- "Fixing" it by wrapping the whole struct in `Rc<RefCell<>>` -- this makes
  the code compile but converts a compile-time-checked invariant into a
  runtime one (`already borrowed` panics), and is strictly worse than
  fixing the shape, because now the same aliasing bug exists but only
  crashes when the aliasing borrows actually happen at runtime instead of
  being caught for every possible path at compile time.
- Cloning the lookup data on every call "just to make it build" -- this is
  fine for genuinely small, cheap-to-clone data but silently becomes an
  O(n) hidden cost on every hot-path call if the cloned structure grows
  later; a clone added to satisfy the borrow checker is easy to forget to
  revisit once the collection it's cloning stops being small.
- Over-correcting into an arena/index-based design for a struct that never
  actually needed self-reference -- if the conflict was pure field
  disjointness (case 2), a full redesign is overkill; destructure the borrow
  instead.

## Verify
After the redesign, confirm `cargo build` succeeds with zero `.clone()` or
`RefCell` additions introduced solely to route around the original error --
if either is still present, check whether it's load-bearing (data really
needs to be shared) or a leftover workaround that the redesign made
unnecessary. Run `cargo clippy` and confirm no new `redundant_clone` or
`rc_clone_in_vec_init`-style lints appear. For arena/index conversions, add
a test that mutates two "related" nodes independently in the same scope to
confirm the new shape actually permits what the old one couldn't.
