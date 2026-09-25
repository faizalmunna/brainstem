---
name: shared-counter-increment-loses-updates-under-concurrency
description: Diagnose a shared counter or accumulator that ends up lower than expected because a read-modify-write increment that looks atomic in source is not atomic at the instruction level.
triggers: ["counter is wrong under concurrent load", "total count lower than expected after parallel processing", "increment operator not thread safe", "lost updates race condition", "counter++ not atomic"]
permissions: ["READ"]
---

## Symptom
A shared numeric variable -- a counter, running total, or accumulator --
updated from multiple threads/workers using what looks like a single
statement (`counter++`, `counter += 1`, `total = total + amount`) ends up
smaller than the number of increments actually performed. The
discrepancy scales with concurrency: it's negligible or absent at low
thread counts and grows worse as concurrency or load increases, and it is
rarely the same wrong number twice, which is the tell that distinguishes
this from an off-by-one logic bug.

## Likely causes
1. **The increment is a read-modify-write sequence, not one instruction**
   -- even a single-token expression like `counter++` compiles to
   separate load, add, and store steps (or their bytecode/interpreter
   equivalent). Two threads can both load the same old value before
   either stores its incremented result, so one increment is silently
   lost -- this is the textbook lost-update race and is the default
   behavior of plain variables in essentially every language unless a
   language-specific interpreter-level lock (like a GIL) happens to make
   the *bytecode* sequence atomic, which itself is not a guarantee for
   compound operations spanning multiple bytecode instructions.
2. **The variable is declared with a visibility-only guarantee, not an
   atomicity guarantee** -- marking a field `volatile` (Java/C#) or
   equivalent ensures every thread sees the latest written value, but does
   nothing to make read-then-write a single indivisible step; teams often
   add this qualifier expecting it to fix the race and are surprised when
   it doesn't.
3. **A lock protects the wrong scope** -- the increment itself is
   protected by a mutex, but the value is also read or written elsewhere
   (e.g. an unprotected fast-path read for a metrics endpoint, or a
   separate reset operation) without holding the same lock, so the
   critical section exists but doesn't cover every access to the shared
   state.
4. **Compiler/runtime reordering or per-thread caching without a proper
   memory barrier** -- even where the increment sequence itself is made
   atomic, a separate thread reading the counter through a stale
   CPU-cache-line copy or a compiler-reordered instruction can observe an
   older value than what actually happened, producing apparent lost
   updates in monitoring/logging even when the counter's own arithmetic is
   correct.

## Diagnose
- Reproduce under deliberately high contention: spin up N threads (N =
  core count or higher) each incrementing the shared counter a fixed
  number of times (e.g. 100,000), join all threads, and compare the final
  value against `N * 100,000`. A plain variable will reliably undercount;
  this isolates the bug from all application logic.
- Inspect the actual compiled/interpreted form of the increment if in
  doubt: disassemble or check bytecode for a load-add-store pattern rather
  than a single atomic-fetch-add instruction.
- Check whether any thread-safety annotation present (`volatile`,
  `synchronized`, a language's "atomic" keyword) actually covers
  read-modify-write semantics for that specific construct, versus only
  guaranteeing visibility of individually read or written values --
  consult the language's memory model documentation for that exact
  qualifier rather than assuming.
- Audit every read and write site of the shared variable, not just the
  increment -- grep the whole codebase for the variable name and confirm
  each access site takes the same lock or uses the same atomic primitive;
  a single unprotected access site anywhere invalidates protection
  everywhere else.

## Fix
Replace the plain read-modify-write with a primitive whose atomicity is
guaranteed by the runtime or hardware for exactly this operation, chosen
by scope:
- For a simple numeric counter, use the platform's atomic integer type
  (`AtomicInteger`/`AtomicLong` in Java, `std::atomic<int>` in C++,
  `atomic.AddInt64` in Go, `Interlocked.Increment` in .NET, a
  `multiprocessing.Value` with a lock or an `atomics` library in Python)
  which performs the fetch-and-add as one indivisible hardware-backed
  operation instead of separate load/add/store steps.
- Where the update is more than a single arithmetic op (e.g. "increment
  only if below a cap," or updating two related fields together), use an
  explicit mutex/lock around the entire read-modify-write block rather
  than reaching for an atomic primitive that only covers one field --
  atomics compose poorly across multiple related values.
- For high-contention hot paths where lock overhead itself becomes the
  bottleneck, consider a per-thread/per-shard partial counter that each
  thread updates without contention, summed only when the total is
  actually read (a striped/sharded counter pattern) -- this trades exact
  real-time accuracy for eliminated contention, which is correct for
  metrics but not for anything requiring an authoritative running total
  (e.g. inventory counts, rate limits) at every instant.
- Ensure every access path -- including "read-only" fast paths, admin
  endpoints, and resets -- goes through the same atomic primitive or lock,
  not just the increment call site.

## Pitfalls
- Adding a visibility-only qualifier (`volatile`) and believing that fixes
  the race, when it only guarantees other threads see the latest value
  once written, not that the read-modify-write sequence itself is
  indivisible -- the lost-update race persists.
- Wrapping only the increment statement in a lock while leaving a
  "fast path" unprotected read elsewhere (e.g. a stats endpoint reading
  the raw field for performance) -- this still lets a torn or stale value
  leak out and, on architectures without word-aligned atomic reads, can
  even produce a value that was never a valid intermediate state.
- Over-correcting by wrapping every single variable access, including
  ones only ever touched from one thread, in a lock or atomic operation
  "to be safe" -- this adds real overhead and contention with no
  correctness benefit for state that was never actually shared.

## Verify
Re-run the same high-contention stress test used to diagnose the bug
(N threads x fixed increments each) and confirm the final value exactly
equals `N * increments_per_thread` across many repeated runs (run it in a
loop dozens of times, not once, since a race can pass by chance on a
single run). Additionally run the test under a race detector where the
language ecosystem provides one (Go's `-race`, ThreadSanitizer for
C/C++/Rust, java.util.concurrent stress-testing tools) and confirm it
reports zero data races on the counter's memory location.
