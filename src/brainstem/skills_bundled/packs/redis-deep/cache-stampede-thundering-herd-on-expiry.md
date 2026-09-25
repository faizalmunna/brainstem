---
name: cache-stampede-thundering-herd-on-expiry
description: A popular cache key's expiration causes many concurrent requests to simultaneously miss the cache and hit the backing database at once, overloading it momentarily.
triggers: ["cache stampede", "thundering herd cache expiry", "database spike when cache key expires", "cache miss overload on ttl expiry"]
permissions: ["READ"]
---

## Symptom

At regular intervals correlating with a popular cache key's TTL
expiration, the backing database or origin service experiences a sharp,
brief spike in load -- many requests arrive simultaneously, all having
missed the cache at the same moment, all independently querying the
backing store to repopulate the same value.

## Likely causes

- **A high-traffic key's TTL expires and the very next request (along
  with every other concurrent request in that instant) sees a cache
  miss**, and with no coordination mechanism, every one of them
  independently queries the backing store and writes the result back,
  multiplying backing-store load by the concurrent request count for that
  brief window.
- **No "single-flight" or lock-based mechanism exists to ensure only one
  request repopulates the cache on a miss** while others wait for that
  result, so the natural concurrency of a popular endpoint directly
  translates into redundant backing-store load on every expiry.
- **Many independently-cached keys share the same or very close TTL
  values** (e.g. all set with the same fixed TTL at roughly the same
  time, such as during a cache warm-up or a deploy), causing many
  different keys' stampedes to align and compound into a much larger
  combined spike than any single key's stampede alone.
- **The backing store query being repeated is itself expensive** (a
  complex aggregation, a slow join), making even a modest multiplication
  of concurrent identical queries disproportionately impactful compared
  to a cheap query experiencing the same stampede pattern.

## Diagnose

1. Correlate backing-store load spikes with the TTL/expiry timing of
   specific high-traffic cache keys to confirm the stampede pattern
   versus an unrelated load source.
2. Check for multiple keys with synchronized or near-identical TTLs that
   might be compounding into a larger combined spike.
3. Measure how many concurrent identical backing-store queries occur
   during a single key's expiry window, to quantify the actual
   multiplication factor.
4. Check whether any existing cache-population logic already has
   locking/coordination, and if so, why it isn't preventing the observed
   stampede (a bug in the lock implementation, or it simply not being
   used for this key).

## Fix

Implement a single-flight/lock-based cache population pattern: when a
request misses the cache, it acquires a short-lived lock (or uses an
atomic "set if not exists" marker) before querying the backing store,
and concurrent requests that see the lock already held either wait
briefly for the result or serve a slightly stale value rather than each
independently hitting the backing store. Add jitter to TTL values (a
small random variation around the base TTL) so many keys don't expire at
exactly the same moment, spreading stampede risk over time rather than
concentrating it. For especially hot keys, consider proactive
refresh-before-expiry (refreshing the cached value slightly before its
TTL actually elapses) so it's never actually allowed to expire under
live traffic.

## Pitfalls

Don't implement locking so coarsely that it serializes unrelated cache
misses for different keys behind the same lock -- scope locks
specifically to the individual key being repopulated. Also don't set TTL
jitter so wide that it defeats the purpose of a predictable cache
refresh cadence for use cases that actually need reasonably fresh data
on a known schedule.

## Verify

Load-test a scenario simulating many concurrent requests at the exact
moment of a hot key's expiry, with the single-flight/jitter fix in
place, and confirm backing-store query volume during that window stays
close to one query (plus reasonable overhead) rather than scaling with
concurrent request count.
