---
name: postgres-transaction-isolation-bugs
description: Diagnose race-condition bugs (double-booking, lost updates, phantom reads) caused by relying on the wrong transaction isolation level or missing explicit locking.
triggers: ["race condition database", "double booking bug", "lost update database", "concurrent transactions bug", "postgres isolation level", "select then update race condition"]
permissions: ["READ", "DATABASE"]
---

## Symptom
Under concurrent load, two transactions that should have been mutually
exclusive both succeed -- two users book the same limited-availability
slot, a "decrement stock, only if positive" operation goes negative, or a
counter/balance ends up wrong after concurrent updates that individually
looked correct.

## Likely causes
1. **Read-then-write race** (a classic "lost update"): a transaction
   reads a value (`SELECT quantity FROM stock WHERE id = ?`), computes a
   new value in application code, then writes it back (`UPDATE stock SET
   quantity = ?`) -- if two transactions do this concurrently, the second
   write can overwrite the first's result based on a now-stale read,
   silently losing one of the updates.
2. **Relying on the default `READ COMMITTED` isolation level's
   guarantees being stronger than they are** -- `READ COMMITTED` (Postgres's
   default) prevents dirty reads but does *not* prevent the lost-update
   pattern above, since each statement sees a fresh snapshot but the
   read and write are still two separate statements with a window between
   them.
3. **No row-level locking on the read** when the subsequent write depends
   on the read value staying valid until the write commits.
4. **A uniqueness/business constraint enforced only in application code**
   (checking "does a booking already exist for this slot" then inserting)
   without a database-level unique constraint backing it up, so the
   check-then-insert race isn't actually prevented by anything atomic.

## Diagnose
- Identify the specific read-then-write sequence: is the "check" and the
  "act" two separate statements/round-trips, with application logic in
  between, rather than one atomic operation?
- Check whether a database-level constraint (unique index, check
  constraint) exists to make the invalid end state impossible regardless
  of timing, or whether correctness depends entirely on application-level
  timing/ordering.
- Reproduce concretely: fire two concurrent requests performing the same
  operation against the same row (a script issuing them in parallel, not
  just "seems to happen sometimes in production") and confirm the bug
  reproduces reliably under real concurrency.

## Fix
- For read-then-write updates, use an atomic, single-statement update
  where possible: `UPDATE stock SET quantity = quantity - 1 WHERE id = ?
  AND quantity > 0` computes and checks in one atomic statement, so
  concurrent transactions can't interleave between a read and a write
  that no longer exists as separate steps.
- Where the logic genuinely can't be expressed as one statement, use
  `SELECT ... FOR UPDATE` to take a row lock on read, so a concurrent
  transaction attempting the same read-then-write blocks until the first
  transaction commits or rolls back, rather than both proceeding on
  stale data.
- Back business-uniqueness rules with an actual database constraint
  (a unique index on `(slot_id)` for a booking table, for example) so the
  invalid state is rejected by the database itself even if application
  logic's check-then-insert has a race window -- catch the resulting
  constraint-violation error and handle it as "already booked," rather
  than relying solely on the pre-check.
- For cases needing true serializable guarantees across multiple
  statements/tables, consider `SERIALIZABLE` isolation for that specific
  transaction, understanding it requires the application to retry on
  serialization failure (Postgres will abort one of the conflicting
  transactions).

## Pitfalls
- `SELECT ... FOR UPDATE` held across a slow subsequent step (an external
  API call inside the same transaction, for example) turns a brief
  necessary lock into a long-held one that hurts concurrency broadly --
  keep the locked transaction as short as possible, doing slow work
  outside it where feasible.
- Switching the whole application to `SERIALIZABLE` isolation "to be
  safe" without handling serialization-failure retries will surface as
  intermittent transaction failures under load that look like a new bug
  -- `SERIALIZABLE` requires retry logic as part of adopting it, not an
  afterthought.
- A unique constraint added as a fix must actually match the real
  uniqueness rule (including any soft-delete or status fields that
  should affect what counts as a duplicate) -- a naive unique index can
  be too strict (blocking a legitimately-new booking after a cancelled
  one) or too loose (missing a status dimension that should matter).

## Verify
Re-run the concurrent reproduction script from the diagnose step against
the fix and confirm the invalid end state (double-booking, negative
stock, lost update) no longer occurs across many repeated concurrent
attempts, not just a single manual test.
