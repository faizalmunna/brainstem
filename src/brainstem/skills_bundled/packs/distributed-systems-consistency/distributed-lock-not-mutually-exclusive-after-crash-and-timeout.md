---
name: distributed-lock-not-mutually-exclusive-after-crash-and-timeout
description: Two processes both believe they hold the same distributed lock after the original holder crashed and a naive timeout released it prematurely.
triggers: ["two workers processing same job simultaneously", "distributed lock not exclusive", "lock expired while holder still running", "duplicate processing despite locking"]
permissions: ["READ"]
---

## Symptom

A distributed lock (implemented via Redis `SETNX`/expiry, a database
row lock with a timeout, a ZooKeeper/etcd lease) is supposed to
guarantee only one process performs some operation at a time, but
under a specific failure sequence two processes end up both believing
they hold it and both perform the operation concurrently -- duplicate
job execution, double-charged payments, or corrupted shared state from
two writers acting simultaneously. It's rare and timing-dependent,
which makes it easy to dismiss after the first occurrence as a fluke.

## Likely causes

- **The lock holder stalls (GC pause, slow I/O, network hiccup, CPU
  starvation) for longer than the lock's timeout/TTL, but is still
  running and unaware its lock expired**; the lock is granted to a
  second process, and when the first process eventually resumes, it
  continues acting as if it still holds the lock because it never
  checked.
- **The lock's timeout was sized for the "normal" case duration of the
  protected operation, without margin for tail-latency scenarios**
  (a slow downstream dependency, a large batch, a cold cache), so
  ordinary variance -- not a crash -- causes legitimate expiry while
  the original holder is still correctly working.
- **The lock implementation itself isn't fencing-token-aware** -- it
  correctly prevents two processes from acquiring the lock
  simultaneously, but doesn't prevent an expired holder's in-flight
  writes from landing after a new holder has already acquired the
  lock and started its own writes, because nothing downstream checks
  which holder's writes are current.
- **Clock or process-pause assumptions are violated across nodes** --
  e.g. a virtualized/containerized environment where the OS scheduler
  can pause a process for an unbounded period (host oversubscription,
  a paused VM), invalidating any timeout logic that assumes bounded
  scheduling delay.

## Diagnose

1. Reconstruct the timeline from lock acquire/release/expiry logs
   (if the lock implementation logs them) or from application logs
   around the incident: when process A acquired the lock, when its
   TTL expired, when process B acquired it, and when process A's
   operation actually completed relative to those events.
2. Check process A's own health signals (GC logs, thread dump if
   available, container/VM scheduling events, CPU throttling metrics)
   for evidence of a pause or stall coincident with the lock expiry.
3. Check the lock TTL configuration against the protected operation's
   p99/p999 duration, not its median -- if the TTL is close to or
   below the tail latency, expiry-while-still-working is expected
   behavior, not an edge case.
4. Check whether the lock implementation supports and is actually
   using a fencing token (a monotonically increasing value returned
   on each acquire) and whether the protected resource validates it,
   or whether "holding the lock" is trusted implicitly with no
   downstream check.
5. Check whether the operation the lock protects is itself idempotent
   -- if it is, concurrent execution may be a correctness non-issue in
   practice even though the locking is technically broken, which
   changes the fix's priority.

## Fix

Attach a fencing token to every lock acquisition (a strictly
increasing number from the lock service) and require the protected
resource -- the database row, the file, the downstream API -- to
reject any write tagged with a token lower than one it has already
accepted. This makes the failure harmless even when a stalled holder
resumes after losing the lock, because its writes carry a stale token
and get rejected, rather than relying on the timeout alone to prevent
overlap. Separately, size the TTL generously against measured tail
latency (not average case) and have the lock holder extend/renew the
lease periodically while still working (a heartbeat), so legitimate
long-running work doesn't trigger false expiry, while a genuinely
crashed or stalled holder still eventually loses the lock. For
operations where fencing tokens can't be threaded through
(third-party APIs with no such concept), make the operation itself
idempotent so duplicate execution is safe regardless of locking
correctness.

## Pitfalls

Don't respond to a single incident by simply raising the TTL to a
very large number -- that only shrinks the*window* for this specific
race while making genuine crash recovery slower (a truly dead holder
now blocks progress for longer), and doesn't address the root cause
that timeout-based mutual exclusion alone can't be made airtight.
Also don't assume a lock library that "supports TTLs" is safe by
default -- many popular Redis-lock recipes (naive `SETNX` + `EXPIRE`)
provide no fencing token at all, and adding a token requires explicit
support both from the lock client and from whatever the lock
protects.

## Verify

Write a test that acquires the lock, artificially pauses the holder
past its TTL (e.g. `SIGSTOP` the process or inject a sleep exceeding
the TTL), allows a second process to acquire the lock, resumes the
first process, and confirms the first process's subsequent write is
rejected by the fencing-token check at the protected resource. Also
load-test the protected operation at its realistic tail latency to
confirm the TTL/heartbeat combination doesn't produce false expiries
under normal, non-crash conditions over a sustained run.
