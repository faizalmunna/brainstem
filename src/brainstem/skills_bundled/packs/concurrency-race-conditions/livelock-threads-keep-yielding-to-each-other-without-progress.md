---
name: livelock-threads-keep-yielding-to-each-other-without-progress
description: Diagnose a system where threads stay actively busy and responsive to each other but make no forward progress because they keep backing off in response to the same conflict.
triggers: ["cpu is pegged but nothing is getting done", "threads keep retrying and backing off forever", "deadlock avoidance made it worse not better", "system busy but throughput is zero", "two processes keep yielding to each other and neither proceeds"]
permissions: ["READ"]
---

## Symptom
Unlike a deadlock, the system is not hung -- CPU usage is high, threads
are actively running, logs show continuous activity (retries, backoffs,
lock attempts) -- but the actual unit of work never completes. Two or
more threads/processes keep detecting a conflict with each other and each
politely backs off or retries in response, only for the same conflict to
recur immediately, indefinitely. This is often introduced *by* a
well-intentioned deadlock-avoidance mechanism (e.g. "if you can't get
both locks, release what you have and retry") that successfully prevents
the hang but replaces it with an equally unproductive spin, which is why
it's frequently discovered right after a deadlock fix ships and CPU usage
spikes without any corresponding increase in useful work.

## Likely causes
1. **Symmetric backoff without randomization or increasing delay** -- two
   threads use identical logic to detect a conflict and immediately
   retry (e.g. "try to lock both resources, if the second fails, release
   the first and try again right away"), and because both threads are
   running the same logic at similar speed, they keep re-colliding at
   almost the same instant indefinitely -- symmetry, not just contention,
   is the specific ingredient that turns ordinary retry-under-contention
   into livelock.
2. **A "polite" resource-release protocol designed to avoid deadlock
   overcorrects into mutual yielding** -- e.g. two threads each try to
   avoid deadlock by yielding whenever they detect the other also wants
   a shared resource, but if both detect the conflict at the same time
   and both yield, neither ever proceeds, and the cycle repeats because
   the conditions that caused both to yield are recreated identically
   each time.
3. **Health-check or supervisory logic fights with itself across multiple
   instances** -- e.g. two nodes in a cluster each detect the other as
   unhealthy and each step back to let the other take over a role
   (leader election, primary/replica failover) using the same criteria at
   the same time, so leadership or ownership never actually settles on
   either one.
4. **Optimistic-concurrency retry storms** -- a compare-and-swap or
   optimistic-locking retry loop (see also the check-then-act and ABA
   skills in this pack) under high contention has every competing thread
   fail and retry at effectively the same rate, so the retry storm itself
   becomes the source of continued conflict rather than external load,
   and throughput approaches zero even though every individual CAS
   attempt is technically "working correctly."

## Diagnose
- Distinguish from deadlock first: confirm via thread/stack dumps taken
  moments apart that thread states are actually changing between samples
  (different stack traces, different lock-attempt targets) rather than
  frozen in an identical blocked state -- livelock shows movement,
  deadlock shows none.
- Measure CPU usage alongside actual completed-work throughput over the
  same window -- high CPU with flat-to-zero completed work is the
  specific signature; if CPU is also low, this is more likely ordinary
  starvation or an unrelated stall, not livelock.
- Log every retry/backoff/yield decision with enough context to
  correlate across threads (timestamp, thread ID, what resource was
  contended, what action was taken), then look for a repeating pattern
  where the same two (or more) threads' decisions alternate in lockstep --
  this confirms the symmetric-collision mechanism directly rather than
  by inference from CPU graphs alone.
- For distributed/multi-process variants (leader election, failover),
  check the actual sequence of ownership-claim and step-down events
  across nodes' logs for an oscillating pattern (A claims, B claims, both
  detect conflict, both step down, repeat) rather than a single node
  successfully holding the role for any sustained interval.

## Fix
Break the symmetry that causes competing parties to make the same
decision at the same time, so at least one side reliably wins a given
round of contention:
- Add randomized backoff (jitter) to any retry-after-conflict logic, so
  the probability of two threads re-colliding at exactly the same moment
  drops sharply after each retry rather than staying constant -- this is
  the standard fix for the retry-storm and symmetric-backoff variants and
  is the same principle behind exponential-backoff-with-jitter in network
  protocols.
- Break ties with an explicit, deterministic priority rule instead of
  identical logic on both sides -- e.g. assign each thread/node a stable
  ID and have the lower-ID (or otherwise consistently ordered) party win
  any detected conflict outright rather than both yielding; this
  guarantees progress because the outcome no longer depends on timing at
  all.
- For distributed leader-election-style livelock, use a
  consensus-backed mechanism (a lease with a fencing token, a
  distributed lock service, or a proper consensus protocol) rather than
  independent nodes each running symmetric self-assessment logic --
  these are specifically designed to converge to a single winner instead
  of oscillating.
- For optimistic-concurrency retry storms under very high contention,
  fall back to a pessimistic lock once the retry count exceeds a
  threshold, rather than retrying the optimistic path indefinitely --
  accept the cost of blocking to guarantee forward progress once
  contention is demonstrably too high for the lock-free approach to make
  headway.

## Pitfalls
- Adding a fixed (non-random) delay before retrying as an attempted fix --
  if both competing threads add the same fixed delay, they simply
  re-collide on the same cadence one step later, reproducing the exact
  livelock with a longer period instead of resolving it; the delay must
  be randomized or otherwise break the symmetry, not just be
  non-zero.
- Fixing the immediate two-thread case observed in an incident without
  checking whether the same symmetric-yielding pattern exists for three
  or more contending parties -- some tie-breaking schemes that correctly
  resolve a two-way conflict (e.g. "higher ID wins") still need
  verification that they converge with N parties rather than just
  producing a different livelock among the remaining contenders.
- Mistaking a fixed livelock for a deadlock fix and removing the
  deadlock-avoidance logic entirely -- reverting to the earlier
  lock-ordering approach that produced the original deadlock is worse
  than a livelock in most cases (a livelock at least allows the option of
  detection and forced tie-breaking; regressing removes even that).

## Verify
Reproduce the original contention scenario (the same two or more
threads/nodes racing for the same resource at high frequency) under the
fix and confirm actual completed-work throughput is now consistently
greater than zero and comparable to the expected rate given available
concurrency, not just that CPU usage looks the same as before. Run the
scenario repeatedly (many trials, not one) to confirm the tie-breaking or
jitter mechanism reliably converges to progress across different random
seeds or timing conditions, since livelock fixes that rely on
probabilistic jitter should be checked across enough trials to rule out
an unlucky recurrence.
