---
name: firestore-hot-document-contention-write-throughput
description: Firestore write throughput to a specific document plateaus far below expectations because many concurrent writers are contending for updates to the same document.
triggers: ["firestore write contention", "firestore hot document limit", "firestore counter update slow", "firestore too much contention error"]
permissions: ["READ"]
---

## Symptom

An application writing frequent updates to a specific Firestore document
(a counter, an aggregate value, a shared status field) sees write
latency increase and throughput plateau well below what Firestore's
overall capacity should support, sometimes with explicit "too much
contention" errors surfaced by the client.

## Likely causes

- **Firestore documents have a practical update rate limit (commonly
  cited around one sustained write per second per document)** due to how
  Firestore's underlying storage handles document-level transactional
  consistency, and a workload writing to a single shared document more
  frequently than that will hit contention regardless of overall cluster
  capacity.
- **Multiple concurrent transactions all attempt to read-modify-write the
  same document** (a common pattern for counters/aggregates), and
  Firestore's optimistic concurrency control causes some of these
  transactions to fail and retry, compounding under higher concurrency.
- **A "hot" document was not anticipated at design time** because the
  access pattern that concentrates writes onto one document only emerged
  as usage grew (a single global counter that seemed fine at low volume
  becomes a bottleneck as traffic scales).
- **Retries on contended transactions are implemented with insufficient
  or no backoff**, causing retry storms that make the underlying
  contention worse rather than resolving it gracefully.

## Diagnose

1. Identify the specific document(s) receiving disproportionate write
   volume via application-level logging or Firestore's own monitoring,
   and confirm the write rate against a single document versus the
   collection-wide rate.
2. Check for explicit contention-related errors in application logs
   (Firestore client libraries typically surface a specific contention
   error type distinct from a generic failure).
3. Review the transaction/write pattern for whether it's genuinely doing
   read-modify-write against a single hot document (like a counter
   increment) versus independent writes that happen to be misattributed
   to contention.
4. Check retry logic for backoff strategy -- immediate, unbacked-off
   retries under contention is a signature amplifying factor.

## Fix

For counter/aggregate-style hot documents, use a sharded counter pattern
-- distribute the value across multiple sub-documents (shards) that can
each be written independently at higher aggregate throughput, and sum
across shards when reading the total. For general hot-document
contention, redesign the data model to spread writes across more
documents where the access pattern allows it (e.g. per-user or
per-time-bucket documents instead of one global document). Implement
proper exponential backoff with jitter on transaction retries so
contention resolves gracefully rather than compounding under a retry
storm.

## Pitfalls

Don't apply a sharded-counter-style redesign to every document
experiencing occasional contention -- it adds real complexity (read-side
aggregation logic, more moving pieces) that's only worth it for
genuinely high-sustained-write-rate documents; for occasional contention,
correct backoff/retry handling alone may be sufficient. Also, when
sharding, choose a shard count that matches actual expected peak write
rate with headroom, since too few shards just moves the same contention
problem to a smaller number of hot sub-documents.

## Verify

Load-test the specific write pattern at the target throughput after
implementing sharding (or backoff), and confirm write latency stays
acceptable and contention errors drop to near zero at the intended
sustained write rate. For a sharded counter, confirm the aggregated read
value stays accurate under concurrent writes across all shards.
