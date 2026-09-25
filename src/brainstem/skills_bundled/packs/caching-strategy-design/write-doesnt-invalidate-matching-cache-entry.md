---
name: write-doesnt-invalidate-matching-cache-entry
description: A write to the source of truth succeeds but the corresponding cache entry is never invalidated, so stale reads persist until the TTL eventually expires on its own.
triggers: ["I updated the record but the API still returns the old value", "cache isn't invalidating after we save", "stale data until the TTL expires then it fixes itself", "why does refreshing eventually show the new value but not right away"]
permissions: ["READ"]
---

## Symptom
A user (or an internal test) updates a record through the normal write path, the database confirms the write, but reads immediately after — or for the next several minutes — still return the old value. Eventually, without anyone touching anything, the correct value appears. The self-healing-after-a-delay pattern is the tell: it means the TTL is what's eventually fixing the problem, not any invalidation logic, because there either isn't any or it isn't hitting the entry that was actually read.

## Likely causes
1. **Missing invalidation call entirely.** A newer write path (a new API endpoint, an admin tool, a batch import, a background job) was added after the caching layer existed, and nobody wired it to call invalidate/delete on write — only the original write path does.
2. **Key derivation mismatch between write and read/invalidate paths.** The read path builds the cache key as `user:{id}:profile` while the invalidation code builds `user:{id}` or includes/excludes a version suffix, locale, or serialization format — they silently target different keys, so invalidation runs successfully against a key nothing ever reads.
3. **Invalidation targets the wrong layer.** The write invalidates the application-level cache but not a CDN or database query-cache layer sitting in front of or behind it, so the stale copy the user actually receives lives in a layer nobody touched (see the multi-layer coordination skill for the broader pattern).
4. **Invalidation happens inside a transaction that can roll back independently of the cache call**, or is fired asynchronously via an event/queue that can be delayed, dropped, or delivered out of order relative to the read.
5. **Denormalized/derived cache entries aren't invalidated by the write that changes their inputs** — e.g., updating a user's name invalidates `user:{id}` but not `post:{id}:author_name` or a list-view cache that embeds the old name.

## Diagnose
1. Grep both the write path and the invalidation/read path for the literal key-construction logic and diff them character-by-character, including parameter order, casing, and any included version/locale/tenant qualifiers — this is the single most common culprit and is often invisible from reading either function in isolation.
2. Add temporary logging (or check existing structured logs) for every cache `set`/`delete` call, including the exact key string, and trace one real write end-to-end to confirm an invalidation call fires at all and targets the same key a subsequent read constructs.
3. Enumerate every code path that writes to this entity (search for the table/model name across controllers, admin panels, background jobs, migrations, bulk import scripts) and check each one individually for a paired invalidation call — don't assume parity across paths.
4. If invalidation is event-driven (e.g., via a message queue or CDC stream), check consumer lag and dead-letter queues for that topic during the affected window to rule out delivery delay or drop.
5. Reproduce directly: perform a write, immediately read the exact cache key with a raw cache client (not through the app), and confirm whether the old value is still present in the cache store itself — this isolates "cache wasn't invalidated" from "cache was invalidated but something else re-populated it with stale data (a race with a concurrent read-through)."

## Fix
Derive the cache key from a single shared function used by every write, read, and invalidate call site — never let key construction be duplicated logic that can drift. Treat invalidation as part of the write operation's contract, not an afterthought bolted onto one call site: wrap writes in a helper that performs the write and its invalidation together, so any new write path that uses the helper gets invalidation for free instead of requiring every future author to remember it. For derived/denormalized entries, maintain an explicit map of "which cache keys does changing entity X affect" (or invalidate by tag/pattern where the cache technology supports it) rather than trying to invalidate exact single keys for every dependent view.

## Pitfalls
Don't fix this by simply shortening the TTL as a safety net "in case invalidation misses something" — that masks the bug, still leaves a window of guaranteed staleness after every write, and adds backing-store load from more frequent expiry, all while the actual key-mismatch or missing-call bug remains and will resurface elsewhere. Fix the invalidation path itself; use TTL only as a last-resort bound on worst-case staleness, not as the correctness mechanism.

## Verify
Write an automated test that performs a write through each known write path, then immediately performs a read through the actual cached read path (not a raw store lookup) and asserts the new value is returned with no sleep or retry. This catches both a missing invalidation call and a key-mismatch, because it exercises the real read path exactly as a user would hit it.
