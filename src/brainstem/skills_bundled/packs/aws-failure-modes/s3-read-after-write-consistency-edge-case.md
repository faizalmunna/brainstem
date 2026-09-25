---
name: s3-read-after-write-consistency-edge-case
description: A just-written S3 object or its updated content appears missing or stale to a read that immediately follows the write in a specific overwrite or list-then-read sequence.
triggers: ["s3 object not found right after upload", "s3 eventual consistency stale read", "s3 list objects missing recent upload", "s3 overwrite returns old version", "s3 404 immediately after putobject"]
permissions: ["READ"]
---

## Symptom
Code writes (or overwrites) an object to S3 and then immediately performs
some follow-up operation that depends on seeing the new state -- a
`GetObject` returns the *previous* version's content, a `HeadObject`
briefly 404s, or a `ListObjectsV2` call right after a batch of uploads
doesn't include one or more of the just-written keys -- even though S3 has
been strongly read-after-write consistent for new object PUTs since
December 2020.

## Likely causes
1. **The operation is actually a read of a *different* representation
   that isn't covered by strong read-after-write consistency** -- e.g.,
   reading through a **CloudFront distribution** in front of the bucket
   (CDN caching, not S3 consistency, is why the old content is served),
   or reading via **S3 Cross-Region Replication** to a replica bucket,
   which is asynchronous and can genuinely lag the source by seconds to
   minutes.
2. **The read is going through a different code path than assumed** --
   e.g., an application-level cache (in-memory, Redis, a signed-URL CDN)
   sitting between the app and S3 that wasn't invalidated on write, wrongly
   attributed to "S3 eventual consistency" when S3 itself already returned
   the new object correctly.
3. **A `PutObject` for the *same key* that's still in flight or retried
   concurrently from another writer** creates a genuine race (last-writer-
   wins at the object-version level), not a consistency bug -- two
   concurrent writers to the same key have no ordering guarantee about
   which one "wins," and the reader may see either, correctly, per S3's
   actual model.
4. **Versioning is enabled on the bucket and the caller reads a specific
   version ID or uses an SDK/library default that doesn't automatically
   target the latest version**, so what looks like a stale read is
   actually a correctly-returned older version because a version ID was
   pinned somewhere (config, cache, or SDK call) upstream.
5. **A `DeleteObject` followed immediately by a `HeadObject`/existence
   check to confirm deletion, or a `PutObject` followed by `ListObjects`
   used as an existence check**, hitting a genuinely rare edge case around
   list-after-write ordering under versioning/lifecycle interactions, or
   simply a client-side retry against a stale connection/cached DNS
   result pointed at an outdated regional S3 endpoint.

## Diagnose
- Confirm whether the read path goes through CloudFront, a signed CDN
  URL, or any application cache before hitting S3 directly -- if so,
  check that layer's cache-control/invalidation behavior first, since
  it is a far more common cause than genuine S3-level inconsistency.
- Check S3 access logs or CloudTrail `data events` for the exact
  `PutObject` and subsequent `GetObject`/`ListObjectsV2` calls, including
  timestamps, request IDs, and (if versioning is enabled) the version ID
  returned by each -- this shows definitively whether S3 itself served
  stale data or whether the issue is elsewhere.
- If cross-region replication is involved, check
  `s3:Replication:OperationCompletedTime` and replication metrics
  (`s3.amazonaws.com` replication CloudWatch metrics or S3 Replication
  Time Control status) to confirm whether the read hit the source or the
  (asynchronously lagging) destination bucket.
- Check whether the bucket has versioning enabled and whether the calling
  code specifies a `VersionId` anywhere (explicitly, or implicitly via a
  cached earlier `HeadObject` response reused later).
- Reproduce with a minimal script doing `PutObject` then immediate
  `GetObject` directly against the S3 API (no CDN, no cache, no SDK
  abstraction) to isolate whether S3 itself is actually the source of the
  staleness.

## Fix
For CDN-fronted content, treat freshness as a CloudFront invalidation or
cache-control problem: set appropriate `Cache-Control`/`max-age` headers
on write, or issue a targeted CloudFront invalidation (or use
versioned/hashed object keys so a "new" object is a new URL rather than
requiring cache invalidation at all) instead of assuming S3 itself needs
a workaround. For application-level caches, invalidate or write-through
the cache at the same time as the S3 write. For cross-region replication
lag, don't read from a replica bucket on a path that requires immediate
consistency with the just-completed write -- read from the source region,
or use S3 Replication Time Control (RTC) if a bounded replication SLA is
required, and design the consumer to tolerate the documented RTC window.
For concurrent-writer races, use conditional writes (`If-Match` /
`If-None-Match` precondition headers, now supported by S3 PutObject) or
S3 Object Lock/versioning with explicit version tracking so the
application controls ordering instead of relying on implicit "the last
PUT wins" behavior. For version-pinning bugs, audit anywhere a
`VersionId` is captured and reused later, and default to unpinned
(latest) reads unless a specific version is intentionally required.

## Pitfalls
Adding artificial delays ("sleep 2 seconds after upload before reading")
to work around what is assumed to be S3 eventual consistency is treating
a symptom that, for direct S3 PUT/GET, hasn't actually existed since late
2020 -- it masks the *real* cause (usually a cache or replication layer)
without fixing it, and the sleep duration is a guess that will eventually
be wrong under different load conditions. Also, conflating S3's strong
consistency for new/overwritten objects with the separate, genuinely
eventual consistency of things like S3 Cross-Region Replication or
CloudFront leads to wrong fixes applied to the wrong layer.

## Verify
Run the isolated repro script (direct `PutObject` then `GetObject` via
the S3 API, no intermediate layers) in a loop under realistic concurrency
and confirm it always returns the latest content. Then verify the actual
production path end-to-end (including CDN/cache) returns fresh content
within the specific, bounded window appropriate to whatever caching or
replication layer was actually responsible, and that this window is
documented and tolerated by the consuming code rather than assumed away.
