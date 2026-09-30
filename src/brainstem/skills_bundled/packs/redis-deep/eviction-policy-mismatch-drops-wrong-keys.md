---
name: eviction-policy-mismatch-drops-wrong-keys
description: Redis evicts keys that the application actually needed to persist because the configured eviction policy doesn't match how the instance is actually being used (pure cache vs. mixed cache-and-store).
triggers: ["redis evicted keys unexpectedly", "redis maxmemory policy wrong", "important redis key disappeared", "redis acting as cache evicting needed data"]
permissions: ["READ"]
---

## Symptom

Data that the application expected to still be present in Redis is
missing -- not expired via an explicit TTL, but evicted because Redis hit
its configured memory limit and removed keys according to its eviction
policy, and the specific keys removed weren't the ones the application
intended to be evictable.

## Likely causes

- **The `maxmemory-policy` is set to a policy that can evict keys with no
  TTL set** (e.g. `allkeys-lru` or `allkeys-random`), but the application
  uses the same Redis instance for both genuinely cache-like data (safe
  to evict) and data intended to persist indefinitely (session tokens,
  rate-limit counters, application state) without TTLs distinguishing
  them.
- **The eviction policy is `volatile-*` (only evicts keys with a TTL
  set), but a critical key was accidentally given a TTL** (a copy-pasted
  `SET` with `EX` from cache-writing code, applied to a key that should
  have been persistent), making it eligible for eviction under memory
  pressure even though it was never meant to be.
- **`maxmemory` is set lower than the actual working set needed for
  legitimately non-evictable data**, so even a correctly configured
  policy has to evict something to stay under the limit, and there's
  nothing "safe" left to evict once genuinely cache-like data is
  exhausted.
- **Redis is being used simultaneously as a cache and as a primary data
  store within the same instance/keyspace**, without a clear separation
  (different instances, different key prefixes with different policies
  where supported) between the two use cases, making a single eviction
  policy fundamentally unable to serve both correctly.

## Diagnose

1. Check the current `maxmemory-policy` and `maxmemory` configuration
   values against actual memory usage at the time data went missing.
2. For the specific missing key(s), check whether they had a TTL set (via
   application logs, or by checking a similar still-present key's TTL if
   the missing one is gone) to determine if `volatile-*` eviction
   targeting TTL'd keys is the mechanism, or if `allkeys-*` evicted a
   TTL-less key.
3. Check Redis's eviction-related stats (`INFO stats` --
   `evicted_keys` counter) to confirm evictions are actually occurring
   and correlate their timing with the missing data.
4. Review application code that writes both the missing key type and any
   genuinely cache-like keys, to see whether they're using the same
   instance/keyspace without a clear separation.

## Fix

Separate genuinely cache-like data (safe to evict, should have a TTL)
from data that must persist (should never be evicted) -- ideally onto
different Redis instances or logical databases with appropriately
different `maxmemory-policy` settings, or at minimum ensure persistent
data genuinely never has a TTL applied and use a `volatile-*` eviction
policy so only TTL'd (intentionally cache-like) keys are eligible for
eviction. Size `maxmemory` based on the actual working set of data that
must never be evicted, plus reasonable headroom for legitimately
evictable cache data. Audit write paths for accidental TTL application to
keys that should be persistent.

## Pitfalls

Don't switch to `noeviction` policy as a blanket fix to prevent any data
loss -- under `noeviction`, Redis will instead start rejecting writes
once memory is full, converting a data-loss risk into an availability
risk, which may or may not be the better tradeoff depending on the
specific use case; make this choice deliberately, not by default.

## Verify

After separating cache and persistent data (or correcting eviction
policy/TTL usage), simulate memory pressure in a non-production
environment and confirm only genuinely intended-to-be-evictable keys are
removed, with persistent data remaining intact even as memory limits are
approached.
