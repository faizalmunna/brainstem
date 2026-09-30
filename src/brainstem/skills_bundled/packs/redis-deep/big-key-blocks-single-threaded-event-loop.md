---
name: big-key-blocks-single-threaded-event-loop
description: A single very large Redis key (a huge hash, set, or list) causes latency spikes across all clients because operations on it block Redis's single-threaded command processing.
triggers: ["redis big key latency spike", "redis blocking on large collection", "redis single threaded slow command", "redis latency spike unrelated key"]
permissions: ["READ"]
---

## Symptom

Redis latency spikes noticeably and affects seemingly unrelated
operations across many different keys and clients, at intervals that
don't correlate with overall traffic volume -- traced to a specific
operation on one particular large key (a hash with hundreds of thousands
of fields, a huge sorted set) that takes long enough to block Redis's
single-threaded command loop and delay everything else queued behind it.

## Likely causes

- **A "big key" accumulated over time** -- a hash, list, set, or sorted
  set that grew far larger than typical because nothing enforces a size
  bound on it (an unbounded cache, a growing list with no trimming), and
  an O(N) operation against it (a full `HGETALL`, `SMEMBERS`, or a
  `DEL` on a huge collection) now takes long enough to be noticeable.
- **A command with worse-than-expected complexity was used against a
  large collection** -- some Redis commands are O(N) or worse and are
  fine on small collections but become a real bottleneck as the
  collection grows, and this wasn't anticipated when the data model was
  designed for what was then a small collection.
- **`DEL` or `EXPIRE`-triggered eviction of a large key blocks the event
  loop** synchronously in older Redis versions or configurations that
  don't use lazy/async freeing (`UNLINK` or `lazyfree` settings), so
  removing a big key is itself a blocking operation proportional to its
  size.
- **No monitoring exists on individual key sizes**, so a big key
  accumulates unnoticed until its impact becomes visible as a general,
  hard-to-attribute latency problem rather than being caught while still
  small.

## Diagnose

1. Use Redis's slow log (`SLOWLOG GET`) to identify which specific
   commands are taking unusually long, and correlate their timing with
   observed latency spikes.
2. Use `redis-cli --bigkeys` (or `MEMORY USAGE` on suspected keys) to
   scan for unusually large keys in the keyspace.
3. Check the data access pattern/application code that created and
   grows the suspected big key, to understand why it grew unbounded --
   missing TTL, no size cap, or an access pattern that should have been
   modeled differently.
4. Check Redis configuration for lazy freeing settings (`lazyfree-
   lazy-expire`, `lazyfree-lazy-eviction`, `UNLINK` usage) to determine
   whether key deletion itself is blocking.

## Fix

Redesign the data model to avoid unbounded single-key growth -- shard a
large hash/set across multiple keys (e.g. by a hash of the field name),
use a bounded structure with explicit trimming (`LTRIM` for lists, or a
sorted set with periodic pruning), or move genuinely large collections to
a data store better suited for them. For necessary operations on large
collections, use cursor-based iteration commands (`HSCAN`, `SSCAN`,
`ZSCAN`) instead of full-collection commands (`HGETALL`, `SMEMBERS`),
since scan-based commands process incrementally without blocking for the
full operation duration. Enable lazy freeing (`UNLINK` instead of `DEL`,
and the corresponding `lazyfree-*` config options) so large key removal
happens asynchronously rather than blocking the main event loop.

## Pitfalls

Don't fix a big-key issue by simply increasing Redis instance size/
resources -- the problem is the single-threaded blocking nature of the
specific operation, not insufficient capacity, so more resources won't
help; the fix must address the operation/data-model, not just scale
hardware. Also don't switch every full-collection read to a scan-based
equivalent reflexively if the collection is genuinely small and bounded
-- scan-based iteration has its own overhead and complexity that isn't
worth it for collections that were never actually a problem.

## Verify

After the fix, use `redis-cli --bigkeys` again to confirm no
similarly-sized keys have accumulated, and monitor the slow log to
confirm operations against the previously-problematic key pattern
(sharded or trimmed) no longer appear as slow-log entries. Monitor
overall Redis latency percentiles to confirm the previously observed
periodic spikes are gone.
