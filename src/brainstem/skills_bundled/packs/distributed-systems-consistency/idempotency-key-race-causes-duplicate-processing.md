---
name: idempotency-key-race-causes-duplicate-processing
description: Two near-simultaneous requests carrying the same idempotency key both pass the not-yet-processed check and duplicate a side effect like a charge.
triggers: ["idempotency key still duplicated request", "double charged despite idempotency key", "duplicate processing with same idempotency key", "race condition in idempotency check"]
permissions: ["READ"]
---

## Symptom

An API implements idempotency keys specifically to prevent duplicate
side effects (charging a payment twice, sending a notification twice,
creating two orders from one checkout click), but duplicates still
happen -- rarely, and almost always correlated with retries firing in
very quick succession (a client-side double-click, an aggressive retry
policy, or a proxy that resends a request whose response was lost).
The idempotency key is present and correct on both requests, which is
what makes this confusing: the mechanism that should have prevented
it was in place.

## Likely causes

- **Check-then-act race in the idempotency store**: the handler reads
  "has this key been processed?", gets "no," and only writes "now
  processed" after performing the side effect -- if two requests with
  the same key run concurrently, both can pass the check before either
  writes the marker, because the check and the write aren't atomic.
- **The idempotency record is written after the side effect completes
  instead of before (or atomically with) it**, so the window during
  which a duplicate can sneak through spans the entire duration of the
  protected operation, not just a few instructions.
- **The idempotency store's write isn't actually unique-constrained**
  -- it's implemented as a read-check-write against a cache or
  document store without a uniqueness guarantee, instead of an
  insert that the datastore itself rejects on collision (e.g. a
  database unique index, a Redis `SETNX`), so "first write wins"
  isn't actually enforced by the storage layer.
- **The idempotency key's scope doesn't match the actual retry
  behavior** -- e.g. a load balancer or client retries at a layer that
  regenerates or omits the key on retry (a proxy strips a header, a
  client library generates a new UUID per attempt instead of reusing
  one), so two "retries" of the same logical request arrive as
  different keys entirely, bypassing the mechanism altogether.

## Diagnose

1. Reproduce directly: fire two requests with the identical
   idempotency key at true concurrency (not sequentially with a small
   delay) using a load-testing tool or a script with parallel threads,
   and check whether the side effect (charge, row insert) happens
   once or twice.
2. Read the idempotency-check implementation and identify exactly
   where the "check" and the "mark as processed" happen relative to
   the side effect -- look specifically for a separate read followed
   by a separate write, rather than one atomic operation.
3. Check whether the idempotency key storage uses a uniqueness
   constraint enforced by the datastore (unique index, conditional
   put, `SETNX`) versus an ordinary read-modify-write that assumes no
   concurrent access.
4. Trace an actual duplicate incident end to end through logs/traces
   to confirm both requests carried the identical key value (ruling
   out the "different retries generate different keys" cause) and
   check the timestamps to measure how close together they arrived.
5. Check any intermediary (load balancer, API gateway, client SDK
   retry logic) for whether it preserves the idempotency key verbatim
   across retries or regenerates/strips it.

## Fix

Make the "claim this idempotency key" step a single atomic operation
against a datastore that enforces uniqueness -- an `INSERT` with a
unique constraint on the key column, or a conditional write (`SETNX`,
DynamoDB conditional put) -- and perform this claim *before* starting
the side effect, not after. Structure the handler so the claim and the
side effect happen within the same transaction where possible (insert
the idempotency record and the resulting side-effect record together,
so a rollback undoes both), or, where the side effect is external
(e.g. calling a payment processor), claim the key first, then perform
the side effect, then record the result against the already-claimed
key -- so a concurrent duplicate request fails the atomic claim
immediately rather than racing past a non-atomic check. For requests
that lose the race, return the result of the original request (poll
or block briefly for it to complete) rather than a generic error, so
retries are transparent to the caller.

## Pitfalls

Don't rely on a cache-based "check if key exists" with a short TTL as
the sole mechanism -- caches typically don't offer the same
uniqueness/atomicity guarantees as a primary datastore's constraints,
and eviction or replication lag on the cache can reintroduce the exact
race being fixed. Also don't scope the idempotency key too broadly
(e.g. per-user-per-day instead of per-logical-request) as a workaround
for key-regeneration issues -- overly broad scoping can incorrectly
collapse two genuinely distinct requests into one, silently dropping
a legitimate second operation instead of preventing a duplicate.

## Verify

Write a concurrency test that fires N simultaneous requests (N >= 10)
with the same idempotency key against the real handler and datastore
(not mocks that hide the race), and assert the side effect's
downstream record count is exactly one and that N-1 requests received
the original result rather than performing their own side effect.
Re-run this test specifically under load (with realistic connection
pool sizes and latency) since some check-then-act races only surface
under real contention, not in a single-threaded unit test.
