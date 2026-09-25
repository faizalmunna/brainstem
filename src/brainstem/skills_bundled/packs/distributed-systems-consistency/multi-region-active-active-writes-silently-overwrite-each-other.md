---
name: multi-region-active-active-writes-silently-overwrite-each-other
description: Concurrent writes to the same record accepted independently by two active-active regions silently overwrite each other with no conflict ever surfaced.
triggers: ["active active regions lost an update", "multi region writes overwrote each other", "conflicting writes across regions no error", "active-active replication silently dropped update"]
permissions: ["READ"]
---

## Symptom

A system runs in an active-active multi-region configuration where
both regions accept writes locally for latency reasons, with
asynchronous cross-region replication reconciling state afterward.
Occasionally, two users (or the same user from two devices/sessions
routed to different regions) update the same record at nearly the
same time, and one of the updates simply vanishes after replication
converges -- no error, no conflict notification, just a record that
doesn't reflect one of the two changes. This differs from ordinary
replication lag because both writes genuinely succeeded and were
acknowledged; the loss happens during conflict reconciliation, not
during transit.

## Likely causes

- **The replication layer's conflict resolution is last-write-wins by
  timestamp**, so of two genuinely concurrent, causally-unrelated
  writes, one is deterministically discarded based on clock value
  regardless of business meaning -- functionally the same mechanism as
  clock-skew LWW issues, but here the root problem is concurrent
  active-active writes being possible at all, not just clock accuracy.
- **The data model doesn't support field-level or operation-level
  merging**, so the resolution strategy is forced to pick one whole
  record version over another rather than merging non-conflicting
  fields from both -- a user who updated their email in region A and
  their phone number in region B loses one of the two changes entirely
  even though they don't actually conflict.
- **Application logic assumes single-region strong consistency and
  never designed for the possibility of concurrent writes to the same
  key**, so there's no application-level conflict detection,
  versioning, or user-facing "someone else changed this" flow -- the
  infrastructure allows concurrent writes but nothing above it expects
  them.
- **Routing isn't sticky per user/session**, so a single user's
  successive actions can land in different regions across requests
  (due to DNS-based geo-routing, a mobile client switching networks,
  or a load balancer with no affinity), manufacturing artificial
  "concurrent" writes from what was actually one user's sequential
  intent.

## Diagnose

1. Reproduce the timeline for a known lost-update incident: pull both
   writes' full records (region of origin, timestamp, causal/version
   metadata if present) and confirm both were genuinely accepted
   before replication reconciled them.
2. Check the replication conflict-resolution configuration/algorithm
   in use (LWW, custom merge function, CRDT-based) and confirm which
   one actually ran for this record type.
3. Check whether the affected record type has any per-field or
   per-operation versioning versus whole-record versioning -- this
   determines whether a field-level merge was even possible or whether
   whole-record LWW was the only option available.
4. Check request routing/session logs for the specific user/session
   involved to determine whether the "concurrent" writes were truly
   independent user actions or artifacts of non-sticky routing
   splitting one user's sequential actions across regions.
5. Query for the frequency of same-key writes landing in different
   regions within a short window across the whole system (not just
   the one incident) to size whether this is a rare edge case or a
   systemic exposure given current traffic patterns.

## Fix

Where the data model allows it, move from whole-record LWW to
field-level or operation-based conflict resolution -- CRDTs
(conflict-free replicated data types) for counters, sets, and other
mergeable structures, or an explicit merge function that combines
non-overlapping field changes from both writes instead of discarding
one entirely. Where true semantic merging isn't feasible, make
conflicts visible instead of silent: version the record (a per-region
vector clock or version counter) and surface a conflict to the
application layer (or the end user, for collaborative-editing-style
use cases) rather than resolving it deterministically and silently.
Add sticky routing per user/session where feasible so that ordinary
sequential single-user actions don't manufacture artificial
cross-region concurrency in the first place, reserving genuine
conflict handling for real concurrent-multi-actor cases. For data
that genuinely cannot tolerate any lost update, reconsider whether it
belongs in an active-active model at all versus routing writes for
that specific record/entity to a single designated region.

## Pitfalls

Don't assume adding "last write wins" is a neutral default just
because it's the path of least resistance -- for any field where a
lost update has real business or user impact (financial fields,
authorization/permission fields), silent LWW is a correctness bug
waiting to be noticed, not an acceptable tradeoff, and should be an
explicit, reviewed decision rather than an unexamined default.
Also don't build conflict *detection* without a follow-through UX or
process for conflict *resolution* -- surfacing "a conflict occurred"
with no defined resolution path just moves the silent data loss to a
silently-ignored notification instead.

## Verify

In a staging multi-region setup, script two near-simultaneous writes
to the same record from two different regions (varying different
fields, then the same field) and confirm the outcome matches the
intended resolution strategy -- non-conflicting field changes from
both writes present, and same-field conflicts either merged
correctly or surfaced as a detectable conflict rather than silently
dropped. Audit production replication-conflict metrics (most
multi-region datastores expose a conflict-resolution counter) over a
representative traffic period to confirm the observed conflict rate
and resolution outcomes match expectations, not just that replication
lag looks healthy.
