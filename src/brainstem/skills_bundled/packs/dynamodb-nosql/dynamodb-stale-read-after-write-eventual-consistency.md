---
name: dynamodb-stale-read-after-write-eventual-consistency
description: A DynamoDB read immediately following a successful write returns old data because the read used eventual consistency instead of an explicit strongly consistent read.
triggers: ["dynamodb read after write returns old data", "dynamodb just wrote item but read shows stale value", "dynamodb ConsistentRead true or false", "read your own writes dynamodb", "dynamodb GSI never strongly consistent"]
permissions: ["READ"]
---

## Symptom
An application writes an item (or an attribute update) successfully --
`PutItem`/`UpdateItem` returns 200 with no error -- and a read performed
moments later, sometimes in the very next line of code or the next
request in a "confirm it saved" flow, returns the *previous* value or
doesn't find the item at all. The write genuinely succeeded (it's
durable), but the specific read replica that answered the read request
hadn't yet received the update, because DynamoDB's default read behavior
is **eventually consistent** -- reads are served from one of multiple
storage replicas chosen for load distribution, not guaranteed to be the
one with the latest write.

## Likely causes
1. **The read explicitly or implicitly uses eventual consistency**
   (`ConsistentRead` defaults to `false` on `GetItem`/`Query` unless set
   otherwise), and the specific replica that answered happened not to
   have propagated the very recent write yet -- typically a
   sub-second-to-low-single-digit-second window, but nonzero.
2. **The stale read is against a Global Secondary Index**, and GSIs
   **only ever support eventually consistent reads** -- there is no
   `ConsistentRead: true` option for a GSI query, unlike the base table or
   a Local Secondary Index, so a "read after write" pattern that queries
   through a GSI cannot be fixed by toggling consistency and needs a
   different approach.
3. **A read-your-writes pattern spans a request boundary that hides the
   timing** -- e.g. a write API call returns success, the client
   immediately issues a separate GET request (possibly hitting a
   different service instance, cache layer, or region), and the
   assumption of immediacy doesn't account for propagation time that
   exists regardless of which specific read call is used.
4. **A DAX (DynamoDB Accelerator) cache layer sits in front of reads**,
   and DAX's write-through behavior aside, item cache TTLs on entries
   populated by *other* readers before the write can still serve stale
   cached data unless the write path specifically goes through DAX too or
   the cache is invalidated.

## Diagnose
- Check the exact read call's parameters for `ConsistentRead` -- if it's
  absent or `false`, that confirms eventual consistency is in play for
  base-table/LSI reads.
- Check whether the read path goes through a GSI (`IndexName` set on the
  `Query`) -- if so, `ConsistentRead: true` isn't a valid option at all
  (the SDK will reject it or the API will error), which redirects
  diagnosis toward index-based staleness rather than a simple flag fix.
- Reproduce with a tight write-then-read loop varying `ConsistentRead`
  between `true` and `false` against the base table directly (not a
  GSI) -- if `true` reliably returns fresh data and `false` intermittently
  doesn't, that isolates the cause to read consistency mode rather than,
  say, a caching layer.
- If a cache (DAX, or an application-level cache) sits between the
  application and DynamoDB, check whether the specific stale read went
  through the cache and whether the write path also went through it (or
  invalidated it) -- a write that bypasses the cache while reads go
  through it reproduces stale reads independent of DynamoDB's own
  consistency model entirely.

## Fix
For reads against the base table or an LSI where genuine read-your-writes
behavior is required (e.g. confirming a save succeeded, or a workflow
step that must see its own prior write), explicitly set
`ConsistentRead: true` on the `GetItem`/`Query` call -- this costs twice
the read capacity of an eventually consistent read of the same size but
guarantees the read reflects all prior successful writes. For reads that
must go through a GSI, since strong consistency isn't available there,
redesign the specific read-your-writes step to read from the base table
(strongly consistent) instead of the index, even if the rest of that
access pattern normally uses the GSI -- or accept and design around the
staleness window (e.g. optimistic UI updates using the data just written
client-side, rather than re-reading it from the index to confirm).
Default to eventual consistency everywhere else, since it's cheaper and
sufficient for the large majority of reads that aren't in an immediate
read-your-writes position.

## Pitfalls
Setting `ConsistentRead: true` globally "to be safe" doubles read
capacity consumption table-wide and doesn't even solve the GSI case (the
option isn't available there), so it's both an incomplete fix and an
unnecessary cost increase for the many reads that were never actually at
risk of the stale-read problem. Also, strongly consistent reads are not
available at all during a regional outage failover in DynamoDB Global
Tables' multi-region replication -- cross-region reads are always
eventually consistent by nature of asynchronous replication, so this
pattern doesn't extend to a "read my write in another region" case
regardless of the `ConsistentRead` flag.

## Verify
Re-run the original write-then-read sequence with `ConsistentRead: true`
set on the affected base-table/LSI read path a statistically meaningful
number of times (hundreds of iterations under realistic timing) and
confirm zero stale reads, versus a nonzero stale-read rate observed with
`ConsistentRead: false` under the same test -- and for any GSI-based read
path that was redirected to the base table, confirm the new code path's
`ConsistentRead` setting and re-run the same test against it.
