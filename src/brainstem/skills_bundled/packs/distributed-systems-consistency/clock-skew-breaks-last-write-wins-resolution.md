---
name: clock-skew-breaks-last-write-wins-resolution
description: Clock skew between nodes causes a last-write-wins conflict resolution strategy to discard the actually-latest write in favor of an older one.
triggers: ["last write wins picked wrong value", "clock skew caused data loss", "wrong value won conflict resolution", "timestamp based conflict resolution incorrect"]
permissions: ["READ"]
---

## Symptom

A system using last-write-wins (LWW) conflict resolution -- common in
multi-master databases, distributed caches, and offline-sync clients
-- occasionally "loses" an update that should have won: a user's more
recent edit is silently overwritten by an older edit from a different
node, with no error and no conflict surfaced to anyone. It's
intermittent and correlates with writes happening on different nodes
close together in time, which is the giveaway that timestamps, not
actual causal order, are deciding the outcome.

## Likely causes

- **Node clocks aren't tightly synchronized** (NTP drift, a node with
  a stopped or misconfigured time-sync daemon, virtualized clocks that
  drift under host contention), so the timestamp attached to a write
  reflects that node's clock, not true wall-clock time -- a write that
  happened later in reality can carry an earlier timestamp if it was
  written on a node whose clock is behind.
- **Timestamps are assigned client-side rather than server-side**, so
  a client with a wrong local clock (common on end-user devices, less
  common but still possible on misconfigured servers) can inject a
  timestamp arbitrarily far in the future or past, permanently
  winning or losing conflicts regardless of actual order.
- **The LWW comparison has insufficient resolution or a naive tie-
  break** -- timestamps truncated to a coarser granularity than the
  actual write rate (e.g. second-level timestamps with sub-second
  write frequency) collide, and the tie-break (often an arbitrary
  field like node ID) doesn't correlate with actual recency at all.
- **Causally related writes are compared as if independent** -- a
  write that was causally derived from reading a previous value (a
  read-modify-write) gets compared purely by timestamp against a
  concurrent unrelated write, discarding real causal information that
  a vector clock or version vector would have preserved.

## Diagnose

1. Check NTP sync status and drift on every node involved in a known
   bad-resolution incident (`ntpstat`, `chronyc tracking`, or the
   cloud provider's time-sync service status) at the time of the
   incident, not just currently.
2. Confirm where the timestamp used for LWW comparison is generated --
   client-side in application code, or server-side at write commit --
   by reading the actual write path, not assuming.
3. Reproduce the specific incident by pulling both conflicting writes'
   full metadata (timestamp, originating node, any version/vector
   clock field if present) and manually determine which one actually
   happened later in real time versus which one the timestamp
   comparison selected.
4. Check the timestamp field's precision/type against the system's
   actual write throughput per key -- if collisions at the stored
   resolution are plausible given the write rate, that's a
   contributing factor independent of clock skew.
5. Audit whether any causal metadata (vector clocks, version vectors,
   a monotonic per-key sequence number) is available but unused by the
   conflict resolution logic, versus genuinely absent from the data
   model.

## Fix

Generate the authoritative timestamp server-side, at the point closest
to actual commit, rather than trusting client-supplied timestamps for
conflict resolution -- if client timestamps are needed for display or
auditing, keep them separate from the field used to arbitrate
conflicts. Tighten and monitor clock synchronization across all nodes
participating in LWW (NTP with monitoring/alerting on drift beyond a
threshold, or a service like Google's TrueTime/AWS's clock-sync
guarantees where available), and treat drift beyond that threshold as
an operational incident, not background noise. Where correctness
actually matters more than the simplicity of LWW, replace pure
timestamp comparison with logical/vector clocks or version vectors
that capture causal "happened-before" relationships, falling back to
wall-clock time (or a domain-specific merge function) only for
genuinely concurrent, causally-unrelated writes. For structured data,
consider CRDTs for fields where merging both updates is possible
instead of picking a single winner and discarding the other entirely.

## Pitfalls

Don't assume tightening NTP alone fully solves this -- even
well-synchronized clocks have inherent drift/precision limits (tens of
milliseconds is normal), so LWW remains unsafe for any workload with
writes to the same key at that frequency or higher, regardless of how
good time sync is. Also don't bolt on a "higher precision timestamp"
(e.g. switching from millisecond to microsecond resolution) as the
whole fix -- it reduces collision probability but does nothing about
the actual clock-skew-causes-wrong-order problem, which is about
accuracy, not precision.

## Verify

In a test environment, deliberately skew one node's clock backward by
a known amount (e.g. via `chronyc` manual offset or a container-level
clock override), perform a write on that node immediately followed by
a genuinely later write on a correctly-synced node, and confirm the
conflict resolution now correctly picks the causally-later write (or
correctly flags them as needing a merge) rather than being fooled by
the skewed timestamp. Add ongoing monitoring that alerts when
inter-node clock drift exceeds the threshold the conflict-resolution
design assumes, so silent drift can't reintroduce the bug.
