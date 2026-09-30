---
name: mongodb-unbounded-array-hits-document-size-limit
description: Diagnose write failures once a MongoDB document's embedded array grows large enough to approach or exceed the 16MB document size limit.
triggers: ["BSON document too large error", "16MB document limit", "document exceeds maximum size", "array field keeps growing and writes started failing", "why did this document stop accepting updates"]
permissions: ["READ"]
---

## Symptom
Writes to a specific document (an `$push` to append to an array field,
or a full document replace) start failing with an error referencing
document size, or updates that used to be fast become slow and
eventually fail outright -- often for "old" or "popular" records (a
long-lived user account, a busy chat thread, a product with years of
reviews) rather than new ones, because the failure only appears once
the array has grown for a long time.

## Likely causes
1. **An array field designed to hold an unbounded, ever-growing list**
   embedded directly in the parent document (e.g. all of a user's
   activity events, all comments on a post, all line items ever added
   to an order) with no cap on how large it can grow, eventually
   approaching the 16MB BSON document size limit.
2. **A "hot" subset of documents grows disproportionately** -- most
   documents in the collection are small and never hit the problem, but
   a small number of outlier documents (a popular post, a long-tenured
   account) accumulate far more array entries than the typical case the
   schema was designed and tested against.
3. **Each `$push` also silently grows write cost even before hitting the
   hard limit** -- MongoDB has to rewrite/relocate the document as it
   grows past its allocated space repeatedly, so performance degrades
   well before the document actually hits the 16MB ceiling, not just at
   the moment of failure.
4. **Denormalized/embedded design chosen for read convenience early on**
   without revisiting it as the access pattern or data volume changed --
   what was a reasonable embed-for-locality decision at small scale
   becomes a structural limit at large scale.

## Diagnose
- Reproduce the failure and check the exact error -- `BSONObj size: X
  (0x...) is invalid. Size must be between 0 and 16793600` (or similar)
  confirms this is the document size limit, not an unrelated write
  error.
- Run `Object.bsonsize(db.collection.findOne({_id: ...}))` (or the
  driver equivalent) on the specific affected document(s) to confirm
  size and identify which field is large.
- Query for the distribution of array length across the collection
  (an aggregation with `$project: { len: { $size: "$theArray" } }`
  and `$group`/percentiles) to confirm whether this is a rare
  long-tail outlier problem or a systemic one affecting most documents.
- Check whether affected documents correlate with age or activity
  volume (older accounts, more popular records) to confirm the growth
  pattern is unbounded accumulation rather than a one-off bad write.

## Fix
- Move the unbounded array out of the parent document into its own
  collection, referencing the parent by ID (e.g. a separate `events`
  or `comments` collection with a `parentId` field and its own index),
  which is the standard "many" side of a one-to-many relationship that
  doesn't fit MongoDB's embedding sweet spot.
- If recent-N access is the actual query pattern (e.g. "show the last
  50 events"), consider the bucket pattern: store fixed-size buckets of
  N array entries per document (one document per time window or per N
  items) instead of one ever-growing array or one document per item --
  this bounds document size while still keeping related data reasonably
  co-located for read efficiency.
- Cap array growth explicitly where the full history isn't actually
  needed embedded (e.g. keep only the most recent N items embedded for
  fast access via `$push` with `$slice`, and archive/query older items
  from a separate collection).
- For the migration itself, backfill existing oversized documents into
  the new structure in batches, and update every write path (not just
  the primary one) to write to the new structure before removing the
  old embedded array.

## Pitfalls
- Switching to `$push` with `$slice` to cap array length solves future
  growth but doesn't fix already-oversized documents -- those need an
  explicit backfill/migration, not just a go-forward schema change.
- Splitting into a child collection without adding an index on the
  parent-reference field (e.g. `parentId`) just trades a document-size
  problem for an unindexed-query problem (see
  `mongodb-unindexed-query-backing-up-job-queue`) when reading the
  related items back.
- Assuming this only affects a few "weird" outlier documents and
  deferring the fix -- the same unbounded-growth pattern will eventually
  affect every long-lived document as it ages, so the fix needs to
  apply to the schema/write path, not just the currently-broken
  documents.

## Verify
After migrating, confirm `Object.bsonsize()` on previously-oversized
documents is now well under the limit with headroom, and run the
aggregation-based array-length distribution check again across the
collection to confirm no document's design allows unbounded growth
going forward (i.e. buckets/child collections are actually being used
on every write path, not just some).
