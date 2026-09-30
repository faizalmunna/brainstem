---
name: mongodb-working-set-thrashing-under-read-load
description: Diagnose catastrophic, sustained load and stalled response times when a read-heavy MongoDB workload's working set stops fitting in memory.
triggers: ["mongodb suddenly slow under load", "mongo cpu and iowait spiking together", "database fine at low traffic falls over at peak", "mongodb page faults climbing", "reads getting slower and slower over the day"]
permissions: ["READ"]
---

## Symptom
A MongoDB-backed service that runs fine most of the day degrades sharply
during a traffic spike or as the dataset grows: read latency climbs,
CPU and disk I/O both spike together, and the system doesn't recover on
its own even after the traffic spike passes -- it stays degraded or falls
over completely, sometimes taking many minutes to hours to recover once
the underlying cause is fixed. This is a distinct pattern from a single
slow query: the *whole instance* degrades, not one endpoint.

## Likely causes
1. **Working set no longer fits in available RAM.** MongoDB's WiredTiger
   cache (and the OS page cache beneath it) keeps frequently-accessed
   documents and indexes in memory; once the actively-queried data
   exceeds available memory, every read that misses cache means a disk
   seek, and disk is orders of magnitude slower than memory.
2. **Low data locality in the access pattern** -- reads are scattered
   across a large fraction of the collection (e.g. a venue/location
   lookup service or a feed touching many unrelated documents) rather
   than concentrated on a hot recent subset, so caching recently-written
   data doesn't help; nearly every read is a potential cache miss.
3. **A positive feedback loop under load**: as more requests queue
   waiting on disk I/O, more concurrent operations compete for the same
   limited cache and I/O bandwidth, which slows every operation further,
   which causes more queuing -- the system doesn't degrade gracefully,
   it collapses, and clearing the traffic spike alone doesn't fix it
   because the cache is now cold and has to be repopulated under
   continued load.
4. **Index working set itself doesn't fit in memory** -- even if document
   data is small, a large collection with several indexes can have an
   aggregate index size exceeding RAM, so even "cheap" indexed lookups
   start faulting to disk.

## Diagnose
- Check `db.serverStatus().wiredTiger.cache` for `bytes currently in the
  cache` vs. `maximum bytes configured` and look at `pages read into
  cache` / `pages requested from the cache` -- a high and climbing
  miss rate correlates directly with the degradation.
- Check `db.serverStatus().extra_info.page_faults` over time (or the
  OS-level `vmstat`/`iostat` for major page faults and disk read IOPS)
  -- a page-fault count that climbs in lockstep with latency confirms
  memory pressure, not a CPU-bound or lock-bound issue.
- Compare total collection + index size (`db.collection.stats()`,
  summing `size` and `totalIndexSize`) against the instance's available
  RAM and configured WiredTiger cache size -- if working set clearly
  exceeds cache size, this is the root cause, not a symptom to treat
  separately.
- Look at query patterns with `db.currentOp()` during the incident:
  many concurrent operations queued and none completing quickly is the
  signature of I/O-bound collapse, as opposed to a few operations stuck
  on a lock.

## Fix
- Size the instance (or cluster) so the actively-queried working set --
  not necessarily the full dataset -- fits comfortably in the WiredTiger
  cache, and budget explicitly for index size, not just document size.
- Increase data locality where the access pattern allows it: partition
  or shard so that related, commonly-co-accessed data lives together and
  a given request touches a narrower slice of the collection, rather
  than scattering reads uniformly across the whole dataset.
- Add read replicas/secondaries to spread read load horizontally once
  memory sizing is fixed -- scaling reads out does not fix an undersized
  working set, it just spreads the same cache-miss problem across more
  nodes unless each node still holds the relevant working set.
- Add backpressure/circuit-breaking at the application layer so that
  under sustained overload the service sheds or queues load gracefully
  (returns errors/slows admission) instead of letting unbounded
  concurrent requests pile onto an already-thrashing database, which is
  what turns a slowdown into a collapse.
- Monitor and alert on cache-miss ratio and page-fault rate as leading
  indicators, not just on overall latency, so capacity issues are caught
  before they cascade.

## Pitfalls
- Treating this as "just add an index" -- an index that's rarely used
  but always resident competes for the same limited cache space as data
  that matters; unused or redundant indexes make effective working-set
  size worse, not better (see `mongodb-compound-index-field-order`
  for a different indexing failure mode).
- Scaling up CPU or adding more application server capacity without
  addressing memory sizing doesn't help -- the bottleneck is disk I/O
  from cache misses, and more concurrent requests hitting a thrashing
  database only deepens the collapse.
- Restarting the mongod process "to clear things up" during an incident
  makes it strictly worse in the short term: it wipes the warm cache,
  so the restarted instance immediately faces the same overload with a
  completely cold cache and even higher page-fault rates.

## Verify
Under a realistic load test (or the next comparable real traffic peak),
confirm the WiredTiger cache hit ratio stays high (miss rate low and
flat rather than climbing) and that `page_faults` and read latency stay
flat as concurrent request volume increases, rather than showing the
prior pattern of latency climbing in lockstep with load.
