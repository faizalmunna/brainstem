---
name: intermittent-deadlock-from-inconsistent-lock-acquisition-order
description: Diagnose an intermittent full hang where two threads acquire the same two locks in opposite order and only deadlock under rare timing or load.
triggers: ["deadlock only happens sometimes", "app hangs randomly in production but not in dev", "two threads waiting on each other forever", "intermittent hang under load", "cant reproduce this deadlock locally"]
permissions: ["READ"]
---

## Symptom
The application hangs completely -- no crash, no error, no log output, CPU
usage drops to near zero for the affected threads/processes -- but only
once in a while, often only under production load, high concurrency, or a
specific request interleaving. It is language- and runtime-independent:
the same shape occurs with OS threads, green threads/fibers, or any
runtime that exposes mutual-exclusion locks. Attempts to reproduce it on a
laptop with light load fail most of the time, which leads teams to
wrongly close the ticket as "couldn't reproduce."

## Likely causes
1. **Classic lock-ordering inversion** -- code path A acquires lock X then
   lock Y; code path B acquires lock Y then lock X. If both paths reach
   their second acquisition before either releases its first, both block
   forever. This requires a specific interleaving, which is exactly why it
   is intermittent -- under low concurrency the two paths rarely overlap in
   the narrow window where both first locks are held simultaneously.
2. **Lock ordering that depends on runtime data rather than source order**
   -- e.g. a "transfer funds between two accounts" function that locks
   `account[from]` then `account[to]` using caller-supplied IDs; two
   concurrent transfers in opposite directions between the same two
   accounts invert the order even though the source code only has one
   lock-acquisition sequence.
3. **A third, indirect lock introduced by a library or framework** -- e.g.
   a logging call, metrics emission, or ORM connection-pool checkout made
   while holding an application lock, where that library internally takes
   its own lock in an order that conflicts with a completely unrelated
   code path also using that library. The deadlock cycle spans code the
   team doesn't own, which is why it's not found by reading application
   code alone.
4. **Load-dependent scheduling exposing a previously-benign window** -- the
   ordering bug always existed, but under low load one thread always
   finishes and releases before the other starts, so the race window is
   never hit; higher thread counts, GC pauses, or scheduler preemption
   widen the window enough to actually interleave.

## Diagnose
- When the hang occurs, capture a full thread/stack dump of every thread
  in the process (`jstack` for JVM, `py-spy dump` for Python, `gdb -p
  <pid>` + `thread apply all bt` for native code, `dotnet-dump analyze`
  for .NET, goroutine dump via `SIGQUIT`/`pprof` for Go). Do this while
  the process is actually hung, not after restarting it.
- In the dump, find every thread blocked trying to acquire a lock (not
  merely idle/waiting on I/O). List, for each blocked thread, which lock
  it wants and which thread currently owns that lock.
- Build the wait-for graph by hand from that list: thread A wants lock
  held by thread B, thread B wants a lock held by thread A (or a longer
  cycle through C, D). A cycle in this graph is a confirmed deadlock, not
  a guess -- most dump tools with built-in deadlock detection (`jstack`
  prints "Found one Java-level deadlock" directly) will name the cycle
  for you.
- Once the two call sites are identified, grep both for every lock
  acquired between entry and the point of blocking, and diff the
  acquisition order between the two paths.
- If the hang cannot be caught live, add a "lock acquired" log line with
  thread ID, lock identity, and a monotonic timestamp around every
  acquisition in the suspect area, then replay the production traffic
  pattern (or its shape: same concurrency level, same request mix) against
  a staging environment tuned to the same core count until it reproduces.

## Fix
Establish one single, global partial order over all locks that can ever be
held simultaneously, and make violating it structurally difficult rather
than relying on developers remembering a convention:
- For a fixed, known set of locks, always acquire them in a documented
  order (e.g. alphabetical by name, or by declaration order in a single
  registry) everywhere in the codebase, and centralize any "acquire both"
  operation behind one function so callers never choose the order
  themselves.
- For data-dependent lock identity (the funds-transfer case), derive the
  order from a stable, comparable property of the resource itself (e.g.
  compare account IDs numerically, always lock the lower ID first)
  regardless of which argument position each ID arrived in.
- Where a strict global order is impractical because the lock set is
  discovered dynamically, use a bounded try-lock-with-backoff pattern:
  attempt to acquire the second lock with a timeout, and if it fails,
  release the first lock entirely and retry the whole operation from
  scratch rather than waiting indefinitely -- this trades a deadlock for a
  detectable, retryable failure.
- Reduce the number of locks held simultaneously in the first place:
  restructure the critical section so a value is read under one lock,
  copied, released, then used to compute the second lock's target,
  narrowing or eliminating the window where two locks are held at once.

## Pitfalls
- "Fixing" it by adding a lock around the whole call chain (a coarser,
  single global lock) -- this does eliminate the ordering deadlock but
  serializes previously-independent work, often turning a rare hang into
  a permanent throughput regression that only shows up as a capacity
  incident weeks later.
- Fixing only the two call sites found in the incident, without adding the
  documented ordering rule or a lint/code-review check -- the same
  ordering bug reappears the next time someone adds a third lock or a
  third code path that touches the same two resources.
- Using a timeout-based `try_lock` as the permanent fix without a retry
  loop that actually redoes the work -- this silently drops or
  partially-applies the operation when the timeout fires instead of
  hanging, which is harder to detect than the original hang because there
  is no visible symptom, only quietly wrong state.

## Verify
Write a stress test that deliberately drives both code paths concurrently
in a tight loop for a fixed duration (e.g. thousands of iterations across
as many threads as the target machine has cores) and assert it completes
within a hard timeout; run it in CI with that timeout enforced so a
regression fails the build loudly instead of hanging the pipeline
silently. Confirm the thread/stack-dump method above now shows zero
blocked-lock cycles when sampled mid-run under the same stress scenario
that previously reproduced the hang.
