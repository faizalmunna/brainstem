---
name: double-checked-locking-exposes-partially-constructed-object
description: Diagnose a rare crash or bad-state bug from a lazily-initialized singleton where another thread observes a partially-constructed object due to missing memory visibility guarantees.
triggers: ["singleton sometimes returns half initialized object", "null pointer on a field that should always be set", "lazy init race condition", "double checked locking bug", "singleton works in dev but breaks under load"]
permissions: ["READ"]
---

## Symptom
A lazily-initialized shared object (commonly a singleton, cache, or
connection pool created on first use) occasionally produces a crash or
corrupted behavior that points to one of its fields being unset, zero, or
null, even though the initializer that sets that field clearly runs
before the object is supposed to become visible. It happens rarely, only
under concurrent first-access (multiple threads racing to initialize the
same shared instance at startup or after a cache eviction), and is
essentially impossible to reproduce with a debugger attached because
the debugger's own overhead changes the timing enough to avoid the race.
Code review often finds a "double-checked locking" pattern already
present, which makes the bug more surprising since it looks like the
race was already handled.

## Likely causes
1. **Missing memory barrier/visibility guarantee on the outer, unlocked
   read** -- the classic broken double-checked-locking pattern checks a
   reference outside any lock, and if that reference is not declared with
   the language's appropriate visibility guarantee (e.g. `volatile` in
   Java/C#, an atomic type with proper ordering in C++/Rust), the CPU or
   compiler is free to make the new object's reference visible to another
   thread *before* that thread also sees the fully-initialized fields
   inside it -- the reference write and the field writes inside the
   constructor can be reordered relative to each other from another
   thread's point of view.
2. **The constructor/initializer publishes `this` before finishing** --
   some initialization code stores a reference to the not-yet-fully-built
   object into a shared location (a registry, a callback, a static field)
   partway through construction, so any other thread reading that shared
   location can observe the object before its own constructor has
   returned, regardless of locking around the outer check.
3. **The inner, locked check re-reads a local variable instead of the
   shared field**, or vice versa, so the "did someone else already
   initialize it" check and the actual publish don't agree on which
   memory location is authoritative, allowing two threads to both believe
   they're the one responsible for initializing and construct two
   separate instances -- functionally different from the visibility bug
   but produces the same class of "impossible" state divergence.
4. **The language/runtime's memory model doesn't provide the ordering
   guarantee developers assume from single-threaded reasoning** -- code
   ported from a language or version where a plain reference assignment
   happened to be safe (or where the runtime's own locking made this
   pattern accidentally correct) breaks silently when moved to a
   different language, a different runtime version, or a more
   aggressively optimizing compiler that takes advantage of relaxed
   ordering the language spec always allowed.

## Diagnose
- Identify the exact pattern: an unlocked read of a shared reference,
  a lock acquired only if that read found nothing, a second read inside
  the lock, and construction-plus-assignment guarded by that lock. Any
  double-checked-locking shape is worth treating as suspect by default
  and verifying against the language's documented memory model rather
  than assuming it's correct because it "looks like the textbook
  pattern."
- Check whether the shared reference field carries the language's
  visibility/ordering qualifier (`volatile` in Java/C#, `std::atomic` with
  at least acquire/release ordering in C++/Rust, or the equivalent). Its
  absence on the outer-check field is the single most common root cause
  and can be confirmed by reading the field declaration alone, with no
  reproduction needed.
- Search the constructor/initializer body for any statement that leaks
  `this` (or an equivalent partially-built reference) to something outside
  the current call stack -- passing `this` to another object's
  constructor, registering a callback, or writing to a field of another
  already-shared object -- before the constructor returns.
- If available, run the code under a memory-model-aware race detector
  (ThreadSanitizer for C/C++/Rust, similar tooling for other ecosystems)
  under a stress test that forces many threads through first-access
  simultaneously; these tools flag the specific unsynchronized
  read/write pair rather than requiring the bug to actually manifest as
  visible corruption.
- Where no such tool exists for the language, reason about it via the
  language specification's memory model documentation directly (e.g.
  the Java Memory Model, the C++ standard's atomics ordering) rather than
  by intuition -- this exact bug is well known specifically because
  intuition from single-threaded code is not a reliable guide here.

## Fix
Choose one of these structurally-correct patterns instead of hand-rolling
unsynchronized double-checked locking:
- Give the shared reference field the language's proper
  visibility/ordering qualifier so the runtime guarantees that once
  another thread observes the new reference, it also observes every write
  that happened-before the reference was published (`volatile` in
  Java/C#, `std::atomic<T*>` with release-store on publish and
  acquire-load on the outer check in C++, an `AtomicReference`/equivalent
  wrapper type). This is the minimal fix that keeps the double-checked
  shape while making it actually correct.
- Prefer the runtime's own guaranteed-once-and-thread-safe lazy
  initialization primitive over hand-rolled double-checked locking
  entirely where one exists (e.g. a language's built-in lazy-static
  mechanism, an initialization-on-demand holder class, a
  `sync.Once`-style primitive, a `Lazy<T>` type) -- these are written and
  reviewed specifically to get this memory-ordering subtlety right, which
  is exactly the part hand-rolled versions get wrong.
- Where lazy, on-first-use construction isn't actually required, sidestep
  the entire class of bug by eager, single-threaded initialization at
  startup before any other thread can possibly access the value.
- If a full lock around every access is acceptable from a performance
  standpoint, drop the "double-checked" optimization entirely and just
  hold the lock for the full check-and-construct-and-read path every
  time -- correctness first, and only reintroduce the unlocked fast path
  with the proper ordering guarantee once profiling actually shows lock
  contention on this path.

## Pitfalls
- Adding `volatile`/an atomic qualifier only to the object reference field
  while leaving mutable fields *inside* the constructed object unguarded
  and mutated after construction from multiple threads -- this fixes the
  publication race but not an entirely separate ongoing data race on the
  object's internals once it's shared.
- Assuming a pattern that "works fine" in one language's memory model
  (or worked fine historically on x86's relatively strong ordering) will
  work identically after porting to another language or running on a
  different CPU architecture (ARM's weaker default ordering surfaces
  reordering bugs that never appeared on x86-only testing) -- always
  verify against the target language and platform's actual guarantees.
- Replacing double-checked locking with a naive plain-boolean "already
  initialized" flag checked outside any lock -- this reintroduces the
  identical visibility problem in a different shape, since a bare boolean
  has no ordering guarantee relative to the object's field writes either.

## Verify
Run a stress test that starts many threads simultaneously, all calling the
lazy accessor for the first time at the same moment (synchronized via a
start barrier so they truly race rather than queue up), and assert every
thread receives a reference to a fully-initialized object (check every
field the constructor sets, not just non-null) across many repeated runs
of the test. Where a race detector is available for the language,
confirm it reports zero data races on the shared reference and the
object's fields during this same stress run.
