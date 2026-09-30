---
name: cosmos-db-session-consistency-stale-read-after-write
description: A client reads back stale data immediately after a successful Cosmos DB write because the session token or consistency level wasn't preserved across requests.
triggers: ["cosmos db read after write stale data", "cosmos db session consistency not working", "cosmosdb write succeeds but read returns old value", "cosmos db eventual consistency unexpected"]
permissions: ["READ"]
---

## Symptom
An application writes a document to Cosmos DB, immediately reads it back
(same logical user action, e.g., "save profile then redirect to profile
page"), and gets the previous version of the document or a 404, even
though the write itself returned success. It's intermittent -- sometimes
the fresh data is there, sometimes not -- and doesn't reproduce reliably
in manual testing from a single client session.

## Likely causes
1. **The account's default consistency level is weaker than the
   application's actual requirement**, e.g., using the default Session
   consistency correctly for a single client but the read-after-write
   pattern spans two different clients/processes that don't share a
   session token (a write from an API server, a read from a different
   service or a different pod instance), so each sees its own consistent
   view but not necessarily the other's most recent write.
2. **The SDK's session token isn't being propagated across requests that
   are logically part of the same user session** -- e.g., a stateless API
   behind a load balancer sends the write and the follow-up read through
   different backend instances, and if the session token returned by the
   write response isn't captured and passed along (either via the SDK's
   automatic session container per client instance, or explicitly via
   `x-ms-session-token` for cross-instance continuity), the read gets
   routed without the guarantee that it reflects that specific write.
3. **The read is targeting a different region than the write in a
   multi-region account**, and replication to that read region hasn't
   caught up yet -- Session consistency guarantees read-your-writes for
   the same session token, but a session token scoped to the write
   region's session doesn't automatically extend the same guarantee
   instantaneously to every other region without the token being
   correctly carried over.
4. **The read uses a different partition key value than the write** (a
   bug, not a consistency setting) -- e.g., a client-side computed
   partition key that doesn't exactly match what was used at write time --
   which looks identical to a staleness problem (the read "doesn't find"
   current data) but is actually a routing/correctness bug unrelated to
   consistency level at all.
5. **A read is served from a local secondary index or a downstream cache
   (e.g., a materialized view maintained via Change Feed) that has its own
   independent lag**, which is a valid architectural tradeoff but gets
   misattributed to "Cosmos DB consistency" when the actual staleness
   source is the derived read path, not the primary container.

## Diagnose
- Check the Cosmos DB account's configured default consistency level
  (Azure portal > Default consistency, or `az cosmosdb show --query
  consistencyPolicy`) and confirm it matches what the application actually
  assumes -- don't assume Session (the default) without checking, since
  some accounts are explicitly configured to Eventual for cost/latency
  reasons.
- Instrument the write and the subsequent read to log the SDK's session
  token (`ISessionContainer`/response headers `x-ms-session-token`) for
  each request and confirm whether the read request actually carries
  forward the token the write returned, especially across any
  service/instance boundary between them.
- If multi-region, check which region each request was routed to
  (response header `x-ms-serviceversion`/diagnostic string from the SDK
  includes contacted region) for the specific write and read pair that
  showed stale data, to confirm whether cross-region replication lag is a
  plausible factor.
- Directly compare the partition key value computed at write time versus
  read time for the specific failing document (log both explicitly) to
  rule out a partition key mismatch masquerading as staleness.
- If a Change Feed-derived read path (materialized view, search index) is
  involved, check its processing lag (Change Feed processor's lease
  checkpoint lag) independently from the primary container's consistency
  behavior.

## Fix
Choose and document a consistency level deliberately based on the
application's actual read-after-write requirements -- Session consistency
is usually sufficient and cost-effective for single-session
read-your-writes needs, but requires actively propagating the session
token across any boundary (load-balanced instances, separate services)
where the write and the dependent read might land on different backend
instances; do this explicitly (capture `x-ms-session-token` from the write
response and pass it on the follow-up read) rather than assuming the SDK's
in-memory session container covers a case it wasn't scoped for. For
genuine cross-region read-after-write guarantees, either route the
dependent read to the same region as the write, or use a stronger
consistency level (Bounded Staleness or Strong) if the latency/cost
tradeoff is acceptable for that specific workload. Fix partition key
computation to be identical and centralized (a single shared function)
between write and read paths rather than independently derived logic that
can drift.

## Pitfalls
Switching the account's default consistency level to Strong globally to
eliminate one read-after-write bug imposes a latency and availability
cost (cross-region write acknowledgment latency, reduced regional
failover flexibility) on every other operation against the account,
often for a problem that only affects a narrow code path -- prefer fixing
session token propagation or scoping a stronger level to the specific
request via the SDK's per-request consistency override instead of
changing the account-wide default. Also, assuming any staleness report is
automatically a Cosmos DB consistency issue without checking for a
Change-Feed-derived cache in the actual read path leads to chasing the
wrong layer entirely.

## Verify
Reproduce the original read-after-write sequence with session token
propagation explicitly wired across the service boundary and confirm the
read consistently reflects the just-completed write across repeated
trials, including trials deliberately routed through different backend
instances. If multi-region, repeat the test with write and read
deliberately targeted at different regions and confirm behavior matches
the chosen consistency level's documented guarantee. Check SDK diagnostics
to confirm the session token is present and non-empty on every dependent
read during the test.
