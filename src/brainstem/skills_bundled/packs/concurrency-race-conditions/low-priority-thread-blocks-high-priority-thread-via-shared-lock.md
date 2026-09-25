---
name: low-priority-thread-blocks-high-priority-thread-via-shared-lock
description: Diagnose a high-priority or latency-critical thread stalling for an unexpectedly long time because it is blocked on a lock held by a lower-priority thread that itself cannot run.
triggers: ["high priority task blocked by low priority task", "priority inversion", "critical thread stalls waiting on background job lock", "realtime deadline missed because of a lock held by low priority worker", "important request stuck behind a lock held by a background task that got deprioritized"]
permissions: ["READ"]
---

## Symptom
A latency-sensitive or high-priority thread/task -- a real-time control
loop, a request-handling thread with a strict SLA, a scheduler's
highest-priority queue -- occasionally misses its deadline or stalls for
far longer than the work it's doing should take, and profiling shows it
blocked waiting on a lock. What makes this distinct from ordinary lock
contention is that the lock is actually held by a *lower*-priority
thread, and that lower-priority thread itself is not running (it's been
preempted by other, medium-priority work), so the high-priority thread is
transitively stalled by threads with no direct relationship to it at all.
This is most visible in systems with explicit thread/task priorities
(real-time OSes, thread-pool priority queues, priority-based schedulers)
but the underlying shape -- important work stuck behind a lock held by
something less important that isn't currently scheduled -- shows up in
any system with priority-aware scheduling.

## Likely causes
1. **Classic priority inversion**: a low-priority thread acquires a lock,
   gets preempted before releasing it because a medium-priority thread
   (unrelated to the lock) becomes runnable, and a high-priority thread
   then blocks trying to acquire the same lock -- the high-priority thread
   is now effectively waiting on the medium-priority thread to finish,
   even though it has no direct dependency on it, because the scheduler
   has no way to know the low-priority lock holder is on the critical
   path for the high-priority thread.
2. **A shared resource used by both background/batch work and
   latency-critical requests without any priority-aware access
   mechanism** -- e.g. a connection pool, cache, or config lock accessed
   by both a low-priority nightly batch job and a user-facing request
   path with no distinction in how they compete for the same mutex.
3. **The scheduler or runtime doesn't support (or the code doesn't use)
   priority inheritance/priority ceiling protocols** -- these are the
   standard mitigations for priority inversion, but they must be
   explicitly enabled or are unavailable in the language/runtime being
   used (many general-purpose application-level mutexes, as opposed to
   real-time OS primitives, simply don't implement priority inheritance
   at all), so the inversion happens by default rather than being an
   unusual misconfiguration.
4. **Priority is set at the thread level but the actual bottleneck is a
   shared, unprioritized queue or thread pool feeding both** -- even
   without an explicit lock, a high-priority task queued behind
   low-priority tasks in a single FIFO work queue serviced by a shared
   worker pool experiences the same practical symptom (importance not
   translating into scheduling precedence) via queueing rather than
   mutex ownership.

## Diagnose
- Confirm the system actually assigns and relies on thread/task
  priorities (real-time scheduling classes, a priority-based executor, a
  weighted queue) -- this bug class specifically requires priority to be
  a meaningful concept in the runtime; if all threads are scheduled
  equally, look at ordinary lock contention or queueing instead.
- Capture a scheduling/thread-state trace at the moment of the stall
  (an RTOS trace tool, `perf sched`, a language runtime's scheduler
  trace) and check three things together: which thread holds the
  contended lock, that thread's priority relative to the blocked
  high-priority thread, and whether the lock holder was actually
  *running* or itself waiting to be scheduled during the stall -- if the
  lock holder is lower-priority and not running because something else
  preempted it, that's the direct signature of priority inversion as
  opposed to ordinary contention.
- Check whether the lock or synchronization primitive in use documents
  priority-inheritance support, and whether it's enabled -- many
  platforms only provide it on a specific primitive type or require an
  explicit flag (e.g. `PTHREAD_PRIO_INHERIT` on POSIX mutexes) rather
  than as a default.
- For the queueing variant, inspect whether high- and low-priority work
  actually share one physical queue/pool versus separate ones, and
  measure how long high-priority items sit queued behind lower-priority
  ones under realistic load.

## Fix
Ensure that holding a shared resource on behalf of high-priority work
cannot be stalled indefinitely by unrelated lower-priority scheduling
decisions:
- Use a lock/mutex implementation that supports priority inheritance (the
  lock holder is temporarily boosted to the priority of the highest
  thread waiting on it, exactly for the duration it holds the lock) where
  the platform provides it, and enable it explicitly if it's opt-in.
- Where priority inheritance isn't available, minimize the time any
  lower-priority thread can hold a lock also needed by high-priority
  work -- shrink that specific critical section aggressively (see the
  oversized-critical-section skill in this pack) so even an unfavorable
  preemption only costs a bounded, short delay.
- Separate resources used by high-priority and low-priority work
  entirely where feasible -- dedicated connection pools, caches, or
  queues per priority class removes the shared-lock dependency that
  makes inversion possible in the first place, at the cost of some
  resource duplication.
- For the queueing variant, use a genuinely priority-aware queue/executor
  (separate queues drained with priority weighting, or a proper priority
  queue data structure feeding the worker pool) instead of a single FIFO
  queue shared across priority classes, so importance actually affects
  scheduling order rather than only being metadata.

## Pitfalls
- "Fixing" it by simply raising the low-priority thread's priority
  permanently -- this defeats the purpose of having it be low-priority at
  all (it now competes equally for CPU with everything else it was meant
  to yield to) rather than solving the specific transitive-blocking
  problem; the fix should be temporary/scoped (priority inheritance) or
  structural (shrink the critical section / separate resources), not a
  blanket priority change.
- Assuming priority inversion is only a real-time-systems concern and not
  checking for it in general application servers -- any system with
  distinguishable request classes (a paid-tier SLA versus best-effort
  background jobs, for instance) sharing infrastructure can exhibit the
  identical shape even without a formal real-time scheduler.
- Adding more worker threads to the shared pool as a generic fix for
  "high priority work is slow" without addressing the underlying shared
  lock or shared queue -- more threads increase the chance a
  medium-priority preemptor exists to trigger the inversion, and can make
  the problem worse rather than better.

## Verify
Reproduce under a controlled scenario: start a low-priority thread
holding the contended lock, introduce medium-priority threads that keep
the CPU busy, and have a high-priority thread attempt to acquire the same
lock; measure its wait time before and after the fix and confirm it now
completes within an expected bound regardless of how much medium-priority
work is contending for the CPU. Where priority inheritance was enabled,
confirm via a scheduler trace that the lock-holding thread's effective
priority is actually boosted while the high-priority thread waits, not
just that the wait time improved by coincidence.
