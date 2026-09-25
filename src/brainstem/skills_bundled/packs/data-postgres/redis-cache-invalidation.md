---
name: redis-cache-invalidation
description: Diagnose stale-cache bugs (Redis or similar) where the cache and the database disagree, and design an invalidation strategy that doesn't just move the bug around.
triggers: ["stale cache bug", "redis cache not invalidating", "cache and database out of sync", "cache invalidation strategy", "old data showing from cache"]
permissions: ["READ", "DATABASE"]
---

## Symptom
Users see outdated data (an old price, a stale status, a value from
before a recent update) even though the underlying database has already
been updated -- the cache is serving a value the database no longer
agrees with, sometimes indefinitely, sometimes only until a TTL
eventually expires.

## Likely causes
1. **Cache invalidation missed on one of several write paths** -- an
   update endpoint correctly invalidates the cache, but a bulk-update
   script, an admin tool, or a background job that also writes to the
   same data doesn't, leaving stale entries that only self-heal on TTL
   expiry (if a TTL exists at all).
2. **TTL set far longer than acceptable staleness**, or no TTL at all, so
   any invalidation gap persists much longer than intended, or forever.
3. **Race between the database write and the cache invalidation**: cache
   is invalidated (or updated) *before* the database write actually
   commits, so a concurrent read repopulates the cache with the
   still-old value between the invalidation and the commit -- the classic
   "cache invalidation race."
4. **Cache key doesn't fully capture what the cached value depends on**
   -- e.g. caching a computed value keyed only on one input when it
   actually depends on several, so a change to an uncounted input isn't
   reflected by any invalidation logic tied to the wrong key.
5. **Invalidating one cache entry when the change actually affects many**
   (a shared aggregate, a list that includes the changed item) -- direct-
   key invalidation handles the single-item case but misses derived/
   composite cached views.

## Diagnose
- Trace every code path that writes to the underlying data and check
  whether each one also invalidates (or updates) the relevant cache
  entries -- list all write paths explicitly rather than assuming the
  "main" one is the only one.
- Check the cache key's inputs against everything the cached value
  actually depends on, to rule out an incomplete key as the cause.
- For a suspected race, reproduce by triggering a write and a
  concurrent read of the same key in quick succession and check whether
  the cache ends up holding the pre-write value afterward.
- Check current TTL configuration (or its absence) against the actual
  acceptable staleness window for this data.

## Fix
- Invalidate (or update) the cache from the single place data actually
  gets written -- centralize writes through one code path/service layer
  responsible for both the database write and the corresponding cache
  invalidation, rather than duplicating invalidation logic (and risking
  missing a spot) across every caller.
- Invalidate (or write the new value) *after* the database transaction
  commits, not before or during -- this closes the race where a
  concurrent read could repopulate the cache with a stale value between
  invalidation and commit. If using write-through caching, ensure the
  cache write happens strictly after the transaction is durably
  committed.
- Set a TTL as a safety net even when explicit invalidation exists, sized
  to the actual acceptable staleness window for that data -- this bounds
  the damage of any invalidation path that gets missed, rather than
  allowing indefinite staleness.
- For derived/composite cached values (aggregates, lists), either
  invalidate by a broader key/tag that captures all affected cache
  entries when any constituent changes, or accept a bounded TTL for
  those specific values instead of trying to enumerate every precise
  invalidation trigger.

## Pitfalls
- Adding a very short TTL "to be safe" everywhere defeats much of the
  performance benefit caching was introduced for -- size TTLs based on
  actual acceptable staleness per data type, not a single blanket default
  applied without consideration.
- Cache-aside (invalidate on write, populate lazily on next read) and
  write-through (update the cache directly on write) have different race
  characteristics and consistency guarantees -- mixing both patterns for
  the same key inconsistently across different code paths reintroduces
  exactly the kind of gap that causes staleness bugs.
- Invalidating too broadly (flushing large portions of the cache on every
  write) as an overcorrection can tank cache hit rate and shift the
  problem to a performance regression instead of a correctness one.

## Verify
Trigger a write through every identified write path (including bulk/
admin/background paths, not just the primary one) and confirm a
subsequent read reflects the new value immediately, with no dependency on
waiting for TTL expiry.
