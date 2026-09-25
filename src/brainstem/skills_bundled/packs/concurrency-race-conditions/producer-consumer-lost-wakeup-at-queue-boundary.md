---
name: producer-consumer-lost-wakeup-at-queue-boundary
description: Diagnose a consumer that goes to sleep waiting for work and never wakes up because a producer's notification arrived in the narrow window just before the wait began.
triggers: ["consumer thread stuck waiting forever even though items were added", "queue has items but worker never picks them up", "lost wakeup", "notify called before wait missed", "worker pool stalls under load then catches up on restart"]
permissions: ["READ"]
---

## Symptom
A producer/consumer queue stalls: items sit in the queue (or a producer
believes it delivered work) while one or more consumer threads are parked
in a "wait for work" state and never wake up, even though the queue is
demonstrably non-empty. The system isn't deadlocked in the classic
mutual-lock sense -- other threads keep running, metrics show the queue
depth climbing -- and it usually self-heals if a new item arrives later
via a different path, or if the stuck consumer is killed and restarted,
which makes it look like a transient blip rather than a reproducible bug.
It gets worse under bursty load and is close to invisible under a slow,
steady trickle of items.

## Likely causes
1. **Classic lost wakeup**: the consumer checks "is the queue empty?",
   sees yes, and is about to call wait/park -- but the producer adds an
   item and sends its wake-up signal in the gap between the consumer's
   check and the consumer actually entering the wait state. Signals in
   most wait/notify primitives are not queued or remembered; a
   notification sent while no one is yet waiting on the condition
   variable is simply lost, so the consumer parks after the signal is
   already gone and has nothing left to wake it.
2. **Waiting without re-checking the condition inside the same locked
   region as the wait call** -- the consumer's emptiness check and its
   call to wait/park are not protected by the same lock held
   continuously across both, so a producer can slip in between them even
   if each half looks individually correct.
3. **Notifying only one waiter (`notify`/`signal`) when multiple consumers
   are parked and the specific one woken doesn't actually take the item**
   -- e.g. it wakes, finds another consumer already grabbed the item via a
   separate fast path, and goes back to sleep without re-arming anything,
   effectively swallowing a wakeup meant for a different item.
4. **A bounded queue's "not full" and "not empty" conditions are handled
   as two independent signals that get crossed** -- a producer blocked on
   "queue full" is only ever woken by a consumer removing an item, and if
   that specific signal path has the same check/wait gap as above, the
   producer side stalls symmetrically to the consumer side, and the
   overall pipeline looks stuck on whichever side hit the gap first.

## Diagnose
- Capture a thread dump while the system is stalled and confirm the
  consumer thread(s) are genuinely parked in the wait/park primitive
  (not blocked on I/O, not spinning) -- this rules out a plain logic bug
  and confirms a signaling issue.
- Check the queue depth/backlog at the same moment: if it's non-zero while
  a consumer sits parked, that's the specific signature of a lost wakeup
  as opposed to a starved consumer or an upstream production stall.
- Read the wait/notify code side by side and verify: (a) the "is there
  work" check and the wait call are executed while holding the *same*
  lock, with no gap where the lock is released between checking and
  actually waiting; (b) the producer's add-item and its notify call are
  also under that same lock, or otherwise guaranteed to happen only after
  the item is visibly enqueued.
- Check whether the condition check on wake is a plain `if` or a `while`
  loop re-checking the condition -- a bare `if` before waiting is a strong
  signal this bug class is present, because it means the code was written
  assuming "wait" reliably blocks until exactly one relevant signal,
  rather than treating spurious/missed wakeups as something to defend
  against by re-checking in a loop.
- Reproduce under an artificially widened race window: insert a small
  deliberate delay between the consumer's emptiness check and its wait
  call (a debug-only sleep), then have a producer add an item during that
  window in a test; if the consumer never wakes, the lost-wakeup path is
  confirmed directly rather than inferred.

## Fix
Use the wait/notify primitive's own condition-variable contract correctly
rather than layering ad hoc flags on top of it:
- Always perform the "should I wait" check and the wait call itself while
  holding the same lock/mutex continuously, so a producer cannot enqueue
  and signal in a gap that doesn't exist -- the lock guarantees the
  producer's enqueue-and-notify is fully serialized against the
  consumer's check-and-wait as one atomic sequence from the condition
  variable's perspective.
- Always re-check the condition in a loop after waking (`while
  (queue.isEmpty()) condvar.wait(lock);` not `if`), because condition
  variables in most runtimes can wake spuriously or be notified for a
  reason that's no longer true by the time this particular thread
  actually resumes and reacquires the lock -- looping is what makes the
  lost-wakeup class of bug and spurious wakeups both harmless.
- Prefer a bounded, well-tested concurrent queue/channel primitive
  provided by the standard library or runtime (a blocking queue,
  channel, or semaphore-backed queue) over hand-rolled wait/notify code
  -- these primitives already encode the "hold lock across check-and-wait"
  and "loop on wake" rules correctly, and hand-rolling this exact pattern
  is one of the most reliably re-invented bugs in concurrent code.
- If a semaphore is more natural for the problem (each item production is
  a release, each consumption an acquire), semaphores count signals
  rather than discarding one sent to no current waiter, which structurally
  avoids the "signal sent before anyone was waiting" failure mode that
  plain condition-variable notify has.

## Pitfalls
- Adding a timeout to the consumer's wait call as the fix ("wake up every
  N seconds and check anyway") -- this masks the symptom by bounding the
  stall duration instead of fixing the race, adds latency up to the
  timeout on every occurrence, and burns CPU on unnecessary polling if the
  timeout is set aggressively to compensate.
- Switching `notify`/`signal` (wake one) to `notifyAll`/`broadcast` (wake
  all) as a blanket fix without also fixing the missing lock-around-check
  problem -- this can hide the lost-wakeup case that happens to have other
  waiters already parked, while leaving the exact scenario where *no one*
  is parked yet (the actual lost-wakeup window) completely unfixed.
- Using a plain boolean "hasWork" flag checked outside any lock as a
  cheap substitute for a real condition variable -- without a memory
  barrier/lock around both the flag's write and its read, a consumer can
  fail to observe the flag's new value at all, independent of the
  wait/notify timing issue.

## Verify
Run the widened-race-window reproduction test (deliberate delay inserted
between check and wait) in a tight loop many times and confirm the
consumer always wakes and processes the item, with zero stalls across
all iterations -- a single passing run is not sufficient evidence given
how narrow the original window was. Separately, run a realistic burst
load test (many producers adding items in a short burst against a small
number of consumers) and confirm queue depth returns to zero without any
external intervention (no restart, no timeout-driven poll) needed to
drain it.
