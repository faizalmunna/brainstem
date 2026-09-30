---
name: shared-cache-across-requests-leaks-tenant-data
description: An in-process cache shared across all requests grows unbounded because it keys on a high-cardinality value like a user or tenant ID with no eviction, effectively leaking one entry per unique caller over the process lifetime.
triggers: ["cache keyed by user id grows unbounded", "in memory cache never shrinks", "per tenant cache entry never evicted", "cache size grows with unique users"]
permissions: ["READ"]
---

## Symptom

An in-process cache (intended to speed up repeated lookups) shows memory
usage that grows in direct proportion to the cumulative number of unique
users, tenants, or request identifiers seen over the process's lifetime
-- rather than staying bounded around the size of the actively "hot"
working set, which is what a well-designed cache should do.

## Likely causes

- **The cache was implemented as a simple unbounded map/dictionary**
  keyed on a high-cardinality identifier (user ID, session ID, tenant
  ID) with no maximum size or eviction policy, so every new unique key
  ever seen adds a permanent entry.
- **A time-based expiration (TTL) was intended but not actually
  implemented or not actually enforced** -- entries are inserted with an
  assumed lifetime but nothing actually removes them once that time
  passes, so TTL exists only as an unenforced intention.
- **The cache was originally sized for a much smaller expected
  cardinality** (a small number of tenants at initial design time) and
  never revisited as the number of unique keys grew significantly with
  business growth.
- **Cache invalidation on the "correct" event (a tenant being deleted, a
  session ending) was implemented, but the cache also accumulates
  entries for events that never trigger that specific invalidation
  path**, so the intended cleanup mechanism only covers part of the
  actual key space.

## Diagnose

1. Confirm the cache's actual current size and growth rate over time,
   and compare against the cumulative unique-key count (unique users/
   tenants seen) over the same period to establish the direct
   correlation.
2. Check the cache implementation for whether it has any maximum size
   limit or eviction policy (LRU, TTL) configured at all, or whether it's
   a plain unbounded map.
3. If a TTL was intended, verify whether expiration is actually checked
   and enforced (a background sweep, a check-on-access pattern) or
   whether entries are simply inserted with a timestamp that's never
   actually acted on.
4. Estimate the actual current and reasonably-expected-future unique key
   cardinality to size an appropriate bound.

## Fix

Replace the unbounded map with a properly bounded cache implementation
(a well-tested LRU or similar eviction-policy cache library) sized to
the actual working-set needs -- the number of "hot" keys likely to be
accessed again soon, not the total cumulative unique key count over the
process's entire lifetime. If TTL-based expiration is the intended
semantics, use a cache implementation that actually enforces it (most
caching libraries provide this correctly built in, rather than requiring
hand-rolled expiration logic).

## Pitfalls

Don't set the cache's maximum size arbitrarily large "to be safe" without
reasoning about actual working-set size -- an oversized bound still
grows unbounded in practice relative to available memory if the
cardinality keeps growing with the business, just with a longer runway
before it becomes a problem; size deliberately based on actual hit-rate
needs versus memory budget.

## Verify

After switching to a bounded cache, monitor its actual size over an
extended period covering significant growth in unique keys seen, and
confirm it stays at or near its configured maximum rather than growing
unboundedly. Confirm cache hit rate remains acceptable at the new bounded
size, verifying the bound wasn't set so small it defeats the cache's
purpose.
