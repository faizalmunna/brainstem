---
name: lock-free-compare-and-swap-fooled-by-aba-problem
description: Diagnose silent corruption in a lock-free data structure where a compare-and-swap succeeds incorrectly because a value changed away and back before the check ran.
triggers: ["lock free stack corrupted", "compare and swap succeeded but state is wrong", "aba problem", "use after free in lock free structure", "cas based algorithm produces corrupted list under concurrency"]
permissions: ["READ"]
---

## Symptom
A hand-rolled lock-free data structure (a Treiber stack, a lock-free
queue or linked list, a custom compare-and-swap-based algorithm) produces
corrupted state under concurrent access despite every individual
compare-and-swap (CAS) operation "succeeding" according to its own
return value -- a node reappears after being removed, a stack ends up
with a cycle in it, a freed/reused memory slot gets referenced after
being recycled, or a counter-based retry loop that should be safe
occasionally produces a wrong result. It is rare, load-dependent, and
notably does *not* show up as a CAS failure -- the bug is that CAS
reports success when the operation was actually unsafe, which makes it
unusually hard to find by adding assertions around CAS failure handling.

## Likely causes
1. **Classic ABA**: thread 1 reads a shared pointer/value A, gets
   preempted; thread 2 changes it to B and then back to A (e.g. popping
   node A off a stack, pushing a different node, then happening to push a
   node that reuses the same memory address or the same value as A);
   thread 1 resumes and its CAS compares against A, sees a match, and
   proceeds as if nothing happened -- but the structure it's pointing
   into (the "next" pointer chain, in the stack example) has actually
   changed underneath it, and the CAS's success is a false positive.
2. **Memory reuse/recycling makes the ABA window practical rather than
   theoretical** -- in languages with manual or pooled memory management,
   a freed node's memory is very likely to be handed back out quickly
   (allocator reuse, a free-list, an object pool), making it common
   rather than astronomically rare for a new allocation to land at the
   exact same address as a just-freed one, which is precisely the
   condition ABA needs to bite.
3. **A version/generation counter is present but not actually included in
   the atomic comparison**, or is too narrow (too few bits, wraps around
   quickly under high throughput) -- some implementations add a counter
   alongside the pointer intending to solve ABA, but if the CAS only
   compares the pointer and the counter is tracked separately (not packed
   into the same atomic word / compared with a proper double-word CAS),
   the counter provides no actual protection.
4. **Reasoning about the algorithm's correctness was based on the CAS
   operation alone**, without considering that a thread can be arbitrarily
   delayed between its initial read and its CAS attempt (preemption, page
   fault, GC pause, or simply being descheduled) -- ABA-safe design
   requires assuming an unbounded delay is possible at that point, not
   just accounting for "normal" scheduling jitter.

## Diagnose
- Identify every CAS-based loop in the code: `read current value -> compute
  new value -> CAS(current, new) -> retry on failure`. For each one, ask
  specifically: if the value at this location changed to something else
  and then back to the original value during the gap between the read and
  the CAS, would the algorithm's invariant still hold? If not, ABA is a
  live risk here regardless of whether it's been observed yet.
- Check whether nodes/memory involved in the CAS'd pointer are ever
  freed and potentially reused (versus permanently retained, e.g. in a
  garbage-collected language where the old node simply becomes
  unreachable but its address is never reused for something else) --
  ABA is far more exploitable in manually-managed or pooled memory than
  in a tracing-GC language, though it remains theoretically possible
  wherever a value (not just a pointer) can cycle back to an
  earlier-observed value.
- Reproduce by deliberately widening the window: insert an artificial
  delay between the read and the CAS in a test build, and drive a second
  thread to perform the exact change-away-and-back sequence during that
  window (pop a node, push an unrelated node, push the original node's
  value back) -- if the CAS then "succeeds" and the structure ends up
  corrupted (verify with an explicit invariant check, e.g. walk the whole
  structure and check for cycles or duplicate nodes), ABA is confirmed
  directly.
- Where a version/tag counter is already present, verify it is packed
  into the *same* atomically-compared unit as the pointer (a
  double-word/tagged-pointer CAS) rather than stored and compared as a
  logically separate field -- a separately-compared counter can itself be
  ABA'd independently of the pointer.

## Fix
Choose a strategy that removes the *possibility* of comparing against a
stale-but-matching value, not one that merely makes it less likely:
- Use a tagged pointer / version-stamped CAS: pack a monotonically
  incrementing generation counter together with the pointer into a single
  value wide enough for an atomic double-word compare-and-swap (many
  platforms and lock-free libraries provide this as `AtomicStampedReference`,
  a tagged/versioned atomic type, or a 128-bit CAS intrinsic), so the CAS
  fails if the value went A -> B -> A even though the pointer alone
  matches, because the tag will have advanced.
- Use a memory reclamation scheme that defers actually freeing/reusing a
  node until no thread could still be holding a reference to its old
  address (hazard pointers, epoch-based reclamation, or a
  read-copy-update-style deferred-free scheme) -- this closes the
  practical exploitability of ABA by ensuring the same address is never
  handed back out while any thread might still be mid-CAS against it,
  even if the logical value could theoretically repeat.
- Where the language provides a garbage collector, prefer relying on it
  to keep old nodes alive as long as any reference (including a
  thread-local snapshot mid-CAS) exists, rather than manually
  freeing/pooling nodes in a lock-free structure -- this sidesteps the
  memory-reuse variant of the problem, though the pure logical-value ABA
  case can still apply to non-pointer values (e.g. a counter that
  wraps).
- Strongly prefer a well-reviewed, existing lock-free data structure
  implementation or concurrency library over writing a new CAS-based
  structure from scratch -- this exact bug class is one of the most
  well-known reasons hand-rolled lock-free code is considered
  higher-risk than equivalent code built on a vetted library, and the
  fix (proper tagging or reclamation) is easy to get subtly wrong even
  when deliberately attempted.

## Pitfalls
- Adding a version counter as a separate, independently-updated field
  next to the pointer without ensuring both are compared atomically
  together -- this looks like an ABA fix in code review but provides no
  actual protection, since the counter and pointer can still be observed
  or updated inconsistently relative to each other.
- Assuming a garbage-collected runtime is automatically immune to ABA --
  it removes the memory-reuse-based variant (a freed node's address
  can't be silently recycled while referenced) but a purely
  value-based ABA (e.g. an integer or enum value that legitimately
  cycles back to a prior value, such as a state machine field) can still
  fool a CAS in any language.
- Choosing hazard pointers or epoch-based reclamation without accounting
  for their own overhead and complexity trade-offs (hazard pointers add
  per-access bookkeeping cost; epoch schemes can delay reclamation
  indefinitely if a thread stalls while holding an old epoch) -- picking
  one without understanding these costs can trade a correctness bug for
  a memory-growth or latency problem.

## Verify
Run the artificial-delay ABA reproduction test used during diagnosis
(force the change-away-and-back sequence during the widened window) and
confirm the operation now correctly retries or fails instead of
proceeding on stale state, verified by walking the full structure for
invariant violations (cycles, duplicate nodes, lost elements) after many
repeated runs. Additionally run the structure under sustained
high-concurrency stress (many threads performing random push/pop or
insert/remove operations for a fixed duration) and verify the final
structure's contents exactly match the expected result derived from a
sequential log of all operations performed.
