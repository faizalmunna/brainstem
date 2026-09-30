---
name: dynamodb-ttl-deletion-delay-items-still-queryable
description: Items past their DynamoDB TTL expiration timestamp are still returned by queries and billed for storage because TTL deletion runs asynchronously with no fixed SLA.
triggers: ["dynamodb ttl expired item still returned by query", "dynamodb time to live not deleting immediately", "dynamodb expired items still in table", "dynamodb ttl deletion delay 48 hours", "why is my expired dynamodb item still showing up"]
permissions: ["READ"]
---

## Symptom
Items with a TTL attribute set to a past Unix timestamp continue to
appear in `Query`/`Scan` results and count toward table storage, well
past the moment the application expected them to be gone. Sometimes this
surfaces as a correctness bug (an "expired" session, cache entry, or
temporary lock is still treated as valid by application logic that
assumes TTL guarantees prompt removal), and sometimes as a cost/capacity
surprise (a table expected to self-prune stays large because deletion is
lagging). The core misunderstanding: DynamoDB's TTL feature deletes
expired items via a **background process with no fixed latency
guarantee** -- AWS documents deletion typically completing within 48
hours of expiration, not immediately at the expiration timestamp, and
under some conditions it can take longer.

## Likely causes
1. **Application logic treats the TTL timestamp as an enforced access
   boundary** -- code assumes that once `expiresAt` is in the past,
   `GetItem`/`Query` will no longer return the item, when in fact TTL only
   guarantees eventual background deletion, not that reads stop returning
   the item the instant it expires.
2. **The TTL attribute is misconfigured** -- stored as a string instead
   of a Number type, stored in milliseconds instead of the required
   Unix epoch seconds, or the wrong attribute name is configured as the
   table's TTL attribute in settings -- any of which causes DynamoDB to
   silently not recognize the item as eligible for TTL expiration at all
   (not a delay, a permanent skip until fixed).
3. **The background TTL deletion process is naturally lagging under a
   large volume of simultaneously-expiring items** -- e.g. a burst of
   items all given the same or similar TTL (common with a fixed session
   duration applied to a traffic spike) creates a expiration bulge that
   takes longer to fully clear than a steady trickle of individual
   expirations would.
4. **Cost/capacity monitoring assumes TTL deletions reduce storage
   immediately at expiration**, so a dashboard or budget alert based on
   "current item count minus known-expired count" undercounts actual
   billed storage during the deletion lag window.

## Diagnose
- Check the table's TTL configuration (`DescribeTimeToLive`) for the
  configured attribute name, and confirm it matches exactly what
  application code writes to.
- Inspect actual item values for the TTL attribute: confirm the type is
  Number (not String) and the value is a Unix timestamp in **seconds**
  (a millisecond timestamp is ~1000x larger and either fails to parse as
  a sane date far in the past/future or expires at the wrong time
  entirely) -- a value that looks like `1789000000000` instead of
  `1789000000` is the direct signature of a seconds/milliseconds mixup.
- Query for items whose TTL timestamp is in the past and check how long
  ago they expired -- if it's within roughly 48 hours, this is expected
  background-deletion lag, not a bug; if items expired far longer ago and
  are still present, that points at a misconfiguration (wrong attribute,
  wrong type) rather than normal lag.
- Check DynamoDB Streams (if enabled) for `REMOVE` events with the
  `userIdentity` field indicating `Service: dynamodb.amazonaws.com` --
  these confirm TTL-driven deletions are actually occurring (vs. never
  happening at all), and their timestamps show real observed deletion
  lag for capacity/cost-planning purposes.

## Fix
Never rely on TTL alone for access-control or correctness-critical
expiration (session validity, lock expiry, rate-limit windows) --
enforce expiration in application read logic by explicitly checking the
TTL/expiry attribute against the current time on every read that cares
about validity, treating TTL purely as an eventual storage-cleanup
mechanism, not an enforcement mechanism. Fix misconfigured TTL attributes
by correcting the type (Number) and unit (seconds since epoch) at the
write path, and re-verify via `DescribeTimeToLive` that the table's
configured attribute name matches. For cost/capacity planning, budget for
the documented deletion lag (up to ~48 hours, potentially more under
heavy simultaneous expiration) rather than assuming immediate storage
reclamation, and if a bulge of simultaneous expirations is a known
pattern (e.g. fixed-duration sessions all created during a traffic spike),
consider jittering TTL values slightly at write time to spread the
resulting deletion load rather than concentrating it.

## Pitfalls
Adding an explicit application-level expiry check is sometimes skipped
because "TTL already handles it," which is exactly the misunderstanding
this skill addresses -- both mechanisms are needed for anything where
serving an expired item is a correctness or security problem (e.g. an
expired auth token item), not just a storage-cost concern. Also, TTL
deletions don't consume provisioned write capacity from the account's
own allocation the way application deletes do, but they do generate
Streams events like any other delete -- a Streams consumer that isn't
built to handle a burst of TTL-driven `REMOVE` events (as opposed to
steady application-driven deletes) can itself become a bottleneck
matching the Streams-retention skill elsewhere in this pack.

## Verify
For a misconfigured-attribute fix, write a test item with a corrected TTL
attribute (Number type, epoch seconds, a few minutes in the future),
confirm via `DescribeTimeToLive` the attribute name matches table
config, then confirm the item is actually removed (absent from
`GetItem`) within the expected background-deletion window -- not
instantly, but within a reasonable multi-hour bound -- rather than
persisting indefinitely as the original misconfigured items did. For the
application-logic fix, confirm reads of an item with a past TTL
timestamp are now rejected/treated as expired by application code
immediately, independent of whether background deletion has physically
removed it yet.
