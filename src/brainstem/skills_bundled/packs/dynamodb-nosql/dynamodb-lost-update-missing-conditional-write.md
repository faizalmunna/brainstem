---
name: dynamodb-lost-update-missing-conditional-write
description: Concurrent writers to the same DynamoDB item silently overwrite each other's changes because updates use unconditional PutItem instead of optimistic locking.
triggers: ["dynamodb lost update race condition", "dynamodb concurrent writes overwrite each other", "dynamodb optimistic locking ConditionExpression", "two requests update same item dynamodb one wins silently", "dynamodb read modify write race"]
permissions: ["READ"]
---

## Symptom
Two (or more) concurrent operations read the same item, each modifies a
different field (or the same field based on its own read), and writes
back -- and one writer's change is silently lost, overwritten by the
other, with no error from DynamoDB and no indication in application logs
that anything went wrong. This shows up as reports like "I updated my
profile but my earlier change to X reverted" or, more severely, financial
or inventory fields that decrement inconsistently under concurrent
requests (double-spend-shaped bugs), because a classic read-modify-write
sequence executed unconditionally.

## Likely causes
1. **Writes use plain `PutItem` (whole-item overwrite) built from a
   locally-held copy of the item**, so Writer A reads the item, Writer B
   reads the same item, both modify their local copy independently, and
   whichever `PutItem` lands last wins entirely -- overwriting the other
   writer's changes to unrelated fields as a side effect of overwriting
   the whole item, not just the field that writer intended to change.
2. **`UpdateItem` is used but without a `ConditionExpression` tied to the
   item's prior state**, so even though `UpdateItem` only touches the
   specified attributes (avoiding the whole-item-overwrite variant of this
   bug), a read-then-decide-then-write pattern (e.g. "read stock count,
   check if >0, then decrement") still races: two concurrent readers can
   both see stock=1, both decide it's available, and both decrement,
   going negative or double-allocating.
3. **No version attribute (or equivalent) exists on the item at all**, so
   there's nothing to condition a write against even if the team wanted
   to add optimistic locking -- the schema itself doesn't support
   detecting a concurrent modification.
4. **DynamoDB Transactions (`TransactWriteItems`) aren't used for
   multi-item invariants**, e.g. "move a value from item A to item B
   atomically" implemented as two separate `UpdateItem` calls -- even if
   each individual call is itself conditioned correctly, the two-call
   sequence isn't atomic as a pair, so a concurrent process can observe or
   interleave with an inconsistent intermediate state.

## Diagnose
- Search write paths for `PutItem` calls that are preceded by a `GetItem`
  read of the same key in application code -- that read-modify-`PutItem`
  shape is the direct signature of an unprotected whole-item overwrite
  race.
- Search `UpdateItem` calls for the absence of a `ConditionExpression`
  parameter, specifically on updates that follow a business-logic
  decision based on a prior read (a balance check, a status check, an
  availability check) rather than a pure blind increment/decrement (which
  DynamoDB's native atomic counters handle safely without conditions).
- Reproduce under load: fire concurrent updates to the same item from
  multiple threads/processes in a test and check whether the final item
  state reflects all intended changes or only the last writer's -- a
  reliable way to expose the race deterministically rather than relying
  on production timing.
- Check for a version/`updatedAt`-style attribute on the item schema --
  its absence confirms there's no mechanism currently in place to detect
  concurrent modification even where it's needed.

## Fix
Add a version attribute (a monotonically incrementing integer, or use the
item's existing `updatedAt` timestamp) and use it in a
`ConditionExpression` on every `UpdateItem`/`PutItem` that follows a
read-modify-write sequence: condition the write on `version = :expectedVersion`
and increment the version as part of the same update. If the condition
fails, DynamoDB returns a `ConditionalCheckFailedException` -- catch that
specifically and retry the read-modify-write cycle (re-read current
state, reapply the business logic, attempt the conditioned write again),
rather than treating it as a hard error. For pure numeric adjustments
(increment/decrement a counter) with no additional business logic
gating them, prefer DynamoDB's native atomic `ADD`/increment update
expressions, which are safe under concurrency without any conditional
logic because the increment happens server-side against the current
value, not a client-held copy. For multi-item invariants, use
`TransactWriteItems` to group the writes (and any conditions) into a
single all-or-nothing atomic operation.

## Pitfalls
Retrying on `ConditionalCheckFailedException` without a bound (infinite
retry loop) turns a correctness bug into an availability one under high
contention -- cap retries with backoff and surface a real error (or a
"please retry" response to the caller) past a reasonable attempt count.
Also, adding a version condition to *some* write paths for an item but
not others (e.g. an admin tool or a batch job still writes unconditionally)
reintroduces the exact same race from the unprotected path -- optimistic
locking only works if it's enforced on every writer touching that item,
not just the primary application path.

## Verify
Re-run the concurrent-write reproduction test (multiple threads/processes
updating the same item simultaneously) and confirm the final item state
reflects a coherent outcome consistent with all intended updates being
applied in some serial order (no silently dropped changes), and confirm
`ConditionalCheckFailedException` is observed and retried (visible in
logs/metrics) rather than writes simply racing silently as before.
