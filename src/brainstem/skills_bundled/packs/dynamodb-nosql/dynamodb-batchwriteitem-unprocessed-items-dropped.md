---
name: dynamodb-batchwriteitem-unprocessed-items-dropped
description: Some items silently fail to write during a DynamoDB BatchWriteItem or BatchGetItem call because the UnprocessedItems response field was not checked and retried.
triggers: ["dynamodb batchwriteitem some items missing", "dynamodb UnprocessedItems ignored", "dynamodb batch write silently drops records", "dynamodb bulk import missing rows no error", "batchgetitem UnprocessedKeys silently skipped"]
permissions: ["READ"]
---

## Symptom
A bulk write job (a data migration, an import, a fan-out write from an
event handler) using `BatchWriteItem` reports success -- the API call
returns a 200 with no exception thrown -- but a fraction of the expected
items never actually made it into the table, and it's inconsistent which
ones. There's no error in logs because `BatchWriteItem` (and
`BatchGetItem`) doesn't throw when individual items within the batch fail
to be processed due to throttling or internal capacity limits -- it
returns those items in an `UnprocessedItems` (or `UnprocessedKeys` for
reads) field in the successful response, and it's the caller's
responsibility to check that field and retry them. Code that only checks
for a thrown exception treats a partially-successful batch as a fully
successful one.

## Likely causes
1. **Application code calls `BatchWriteItem` and checks only for a thrown
   exception**, never inspecting the response body's `UnprocessedItems`
   map, so any items DynamoDB internally throttled or couldn't process
   within that batch call are dropped without any code path noticing.
2. **The batch is large or hits a partition that's under load**, making
   partial throttling within a single batch call more likely -- unlike a
   single-item `PutItem`, which either succeeds or throws, a 25-item
   `BatchWriteItem` can have most items succeed and a handful throttle
   simultaneously, since DynamoDB processes each item independently
   within the batch and reports per-item outcomes rather than an
   all-or-nothing result.
3. **A retry loop exists but has no bound or backoff**, so under
   sustained throttling it either spins indefinitely (availability
   problem) or, more commonly in an unbounded try-once-and-move-on
   pattern, the retry attempt itself isn't actually wired up despite
   looking like it should be -- e.g. the code calls
   `BatchWriteItem` in a loop over input chunks but never feeds
   `UnprocessedItems` from one call back into a subsequent request.
4. **`BatchWriteItem` is assumed to behave like a transaction** (all-or-
   nothing), leading teams to skip building retry/idempotency handling
   under the mistaken belief that a 200 response guarantees every item in
   the batch was written -- `BatchWriteItem` explicitly provides no
   transactional guarantee across its items, unlike `TransactWriteItems`.

## Diagnose
- Review the `BatchWriteItem`/`BatchGetItem` call sites in code for
  whether the response's `UnprocessedItems`/`UnprocessedKeys` field is
  read at all -- its complete absence from the code path is the direct
  confirming signal.
- Reproduce under load: run a batch write of items against a table with
  deliberately low provisioned capacity (or targeting a single hot
  partition) and inspect the actual SDK response for a non-empty
  `UnprocessedItems` map, confirming the API does return partial failures
  under realistic throttling conditions.
- Cross-check a specific known-missing item: query for it directly after
  the "successful" batch job completed, and check CloudWatch
  `ThrottledRequests` for the table around the time the batch ran to
  correlate the drop with a throttling event rather than a logic bug
  elsewhere.
- Check whether the batch job logs total items submitted versus total
  items the code actually confirmed as processed (not just "batch call
  didn't throw") -- most silent-drop incidents surface as soon as that
  comparison is added, even before root-causing further.

## Fix
Always check `UnprocessedItems` (or `UnprocessedKeys`) on every
`BatchWriteItem`/`BatchGetItem` response and retry exactly those items in
a subsequent call, using exponential backoff with jitter between retry
attempts, bounded by a maximum retry count after which the still-
unprocessed items are logged/routed to a dead-letter mechanism for manual
or automated follow-up rather than silently dropped. Most current AWS
SDKs offer a higher-level batch-write helper (e.g. a DynamoDB document
client's batch writer in some SDKs) that handles this retry loop
internally -- prefer that over hand-rolled `BatchWriteItem` calls where
available, but verify the specific SDK/language binding in use actually
provides it, since not all do. For workloads that need an actual
all-or-nothing guarantee across multiple items (not just "eventually all
processed"), use `TransactWriteItems` instead of `BatchWriteItem` --
transactions fail the entire group atomically rather than partially
succeeding, which is a fundamentally different guarantee than
batch operations provide.

## Pitfalls
`TransactWriteItems` is not a drop-in replacement for `BatchWriteItem` in
all cases -- it has a lower per-call item limit, costs roughly double the
write capacity (transactions consume 2x WCU per item versus standard
writes), and an entire transaction fails if any single condition fails,
which is the opposite behavior of wanting "process what you can, retry
the rest." Choose based on whether the workload actually needs atomicity
across the group or just needs all items eventually written. Also, a
naive retry loop that doesn't apply backoff can worsen throttling by
hammering an already-struggling partition with immediate retries,
compounding the original problem instead of recovering from it.

## Verify
Run the same load-inducing reproduction (batch write against
under-provisioned/hot capacity) with the fixed retry logic in place, and
confirm every originally-submitted item is present in the table afterward
via a direct count/query comparison against the submitted count -- not
just confirming the API calls didn't throw. Confirm logs show any items
that needed retries were retried and eventually succeeded (or were
explicitly routed to a failure-handling path after exhausting retries),
rather than disappearing from visibility either way.
