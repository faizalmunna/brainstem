---
name: oversized-critical-section-serializes-concurrent-work
description: Diagnose severe throughput loss and lock contention caused by holding a lock across expensive I/O or computation far longer than the actual shared-state access requires.
triggers: ["throughput drops as concurrency increases", "adding more threads makes it slower not faster", "lock contention under load", "requests queue up behind a single lock", "why is this endpoint serialized"]
permissions: ["READ"]
---

## Symptom
A system that should scale with added threads/workers instead plateaus or
gets slower as concurrency increases -- request latency climbs, thread
pools fill up with workers blocked waiting for a lock, and profiling or
lock-contention metrics point at one specific lock as the bottleneck.
Unlike a deadlock, nothing hangs forever; work still completes, just far
slower than the available parallelism should allow, and it's often
misdiagnosed first as "we need more threads" or "the database is slow,"
because the actual I/O or computation happening inside the lock looks
individually reasonable in isolation.

## Likely causes
1. **A network call, disk I/O, or database query is made while holding the
   lock**, when only an in-memory read or write of shared state actually
   needs protection -- every other thread wanting the same lock now waits
   for the full round-trip latency of that external call, not just for a
   memory operation, turning a microsecond-scale critical section into a
   millisecond- or second-scale one.
2. **Expensive computation (parsing, serialization, compression, a large
   loop) happens inside the locked region** because it was easiest to
   write the whole operation as one method wrapped in a single
   lock/synchronized block, rather than separating "compute the new
   value" from "publish the new value under lock."
3. **A coarse, single lock protects an entire object or subsystem** when
   only a small, specific piece of state actually needs mutual exclusion
   -- e.g. one lock for an entire cache instead of per-key or sharded
   locks, so unrelated keys contend with each other even though they
   share no actual state.
4. **Logging, metrics emission, or a callback/event-handler invocation
   happens inside the critical section** -- these are easy to overlook as
   "just a log line" but can involve I/O (writing to disk, a network sink)
   or invoke arbitrary user-supplied code of unknown cost, both of which
   extend the lock hold time unpredictably and can even reintroduce a
   lock-ordering hazard if the callback itself tries to acquire a lock.

## Diagnose
- Use lock-contention profiling appropriate to the runtime (Java Flight
  Recorder / `async-profiler`'s lock profiler, `perf lock`, a mutex
  wait-time histogram from the language's concurrency library, or simply
  instrumenting lock acquire/release with timestamps) to identify which
  specific lock has the highest cumulative wait time under load, rather
  than guessing from source code alone.
- For that lock, measure actual hold duration in production or a
  realistic load test (log a monotonic timestamp at acquire and release,
  or use the profiler's hold-time metric) and compare it against the
  hold duration expected for a pure in-memory operation (sub-microsecond
  to low-microsecond range) -- a hold time in the millisecond range or
  higher for what should be a memory operation is the direct signature of
  this bug.
- Read the code inside the critical section line by line and classify
  each statement as "touches the shared state that needs protecting" or
  "does something else" (I/O, computation independent of the shared
  state, calls into other code) -- anything in the second category is a
  candidate to move outside the lock.
- Check whether throughput actually degrades as concurrency increases in
  a load test (fixed workload, increasing thread/worker count) -- a
  throughput curve that flattens or inverts past a certain concurrency
  level, correlated with rising lock-wait time from the profiler, confirms
  this is a critical-section-size problem rather than a downstream
  capacity limit.

## Fix
Shrink the critical section to cover only the operations that actually
require mutual exclusion over the shared state, restructuring the
surrounding code so everything else happens outside the lock:
- Move I/O (network calls, disk reads/writes, database queries) entirely
  outside the lock: perform the I/O first, compute the result, and only
  acquire the lock briefly to read or update the shared state with that
  already-computed result.
- Move pure computation that doesn't depend on the protected shared state
  outside the lock in the same way -- compute the new value, then lock
  only to swap/publish it in.
- Replace one coarse lock over an entire structure with finer-grained
  locking scoped to the actual unit of contention -- per-key locks (a
  striped lock map), sharding a cache or counter across N independently
  locked partitions, or a read-write lock where the workload is
  read-heavy so concurrent readers don't block each other at all.
- Where the protected value is read far more often than written,
  consider a copy-on-write or immutable-snapshot pattern: readers get a
  reference to an immutable snapshot without any lock at all, and writers
  build a new snapshot and swap the reference under a brief lock,
  eliminating reader contention entirely.
- If a callback or user-supplied code must run as part of the operation,
  invoke it after releasing the lock (queue the notification, release,
  then invoke) rather than from within the locked region, accepting that
  the callback then sees slightly stale state rather than blocking every
  other lock holder on arbitrary external code.

## Pitfalls
- Splitting one critical section into several smaller ones without
  checking whether the operation as a whole still needs to be atomic --
  shrinking the lock scope can silently reintroduce a check-then-act race
  or a lost-update bug between the now-separate locked regions if the
  overall operation actually required end-to-end atomicity.
- Switching to finer-grained locking (per-key/striped locks) without
  addressing operations that need to touch multiple keys atomically (e.g.
  a "move value from key A to key B" operation) -- this reintroduces a
  lock-ordering hazard across the newly-separate locks that didn't exist
  under the single coarse lock.
- Removing the lock's protection over a piece of state because "it's only
  read after this point" based on a static read of the code, without
  verifying no other code path writes to it concurrently -- shrinking a
  critical section requires re-deriving exactly which reads and writes
  are actually racing, not just visually trimming the block.

## Verify
Re-run the same load test used to diagnose the bug (fixed workload,
increasing concurrency) and confirm throughput now scales up to a
meaningfully higher concurrency level before plateauing, with lock-wait
time from the profiler dropping to match the expected in-memory-operation
hold time. Separately, run a correctness stress test targeting the
now-smaller critical section specifically (concurrent writers/readers
hammering the same shared state) to confirm no new check-then-act or
lost-update race was introduced by the refactor.
