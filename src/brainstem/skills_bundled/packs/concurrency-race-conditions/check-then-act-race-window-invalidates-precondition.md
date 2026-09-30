---
name: check-then-act-race-window-invalidates-precondition
description: Diagnose a bug where code checks a condition and then acts on it, but another thread changes the condition in the gap between the check and the act.
triggers: ["time of check to time of use bug", "file existed when i checked but then it didnt", "duplicate row inserted despite checking first", "race between check and update", "toctou race condition"]
permissions: ["READ"]
---

## Symptom
Code that first checks a condition ("does this file exist," "is this slot
empty," "is this balance sufficient," "does this record already exist")
and then performs an action based on that check occasionally behaves as
if the check never happened -- a file operation fails because the file
was deleted after the check but before use, a duplicate record gets
created despite an existence check, a resource is double-allocated
despite a "is it free" check, or a balance goes negative despite a
"sufficient funds" check. It happens rarely and disproportionately under
concurrent load, and the failure looks like the guard condition was
skipped entirely, which is confusing because the code clearly contains
the guard.

## Likely causes
1. **The check and the act are two separate operations with no atomicity
   between them (classic TOCTOU -- time-of-check to time-of-use)** -- any
   other thread, process, or even the OS/filesystem can act in the gap
   between the check returning and the subsequent action executing, no
   matter how small that gap looks in source code; there is no such thing
   as "close enough" for this class of bug.
2. **The check and act use different scopes or different locks** -- the
   check reads state under one lock (or no lock) and the act happens under
   a different lock, or after that lock is released, so the two operations
   are individually safe but not atomic as a pair -- a very common mistake
   when developers correctly protect each operation individually but treat
   "protected read" plus "protected write" as equivalent to "protected
   read-then-write."
3. **The check queries an external system (database, filesystem, cache)
   whose state can change out-of-band** -- a uniqueness check via `SELECT`
   followed by a separate `INSERT` races against any other client of the
   same database doing the same sequence concurrently; the database has
   no idea the two statements are meant to be one logical operation unless
   told so explicitly.
4. **Retry or fallback logic re-runs the check but not atomically with the
   retried action** -- error-handling paths that re-verify a precondition
   before retrying often reintroduce the exact race the original code
   path was trying to avoid, because the "safe" retry path was written
   later and less carefully than the main path.

## Diagnose
- Identify every place where a condition is read and a decision made from
  it, then trace forward to find the actual mutating action -- if there is
  any code between the read and the write that yields control (a function
  call into other code, an I/O call, a lock release, an `await`/yield
  point, or simply a non-trivial number of instructions under real
  concurrency), the window exists regardless of how narrow it looks.
- For database-backed checks, look specifically for a `SELECT` (existence
  or uniqueness check) followed by a separate `INSERT`/`UPDATE` statement
  in application code rather than a single constraint-enforcing statement
  -- grep for patterns like "find by X, if not found then create."
  Reproduce by firing two identical requests concurrently (e.g. with a
  short artificial delay inserted between the check and the act to widen
  the window on purpose) and confirm both proceed past the check.
- For filesystem operations, check for a stat/exists call followed by a
  separate open/write/delete call rather than an atomic
  "create-if-not-exists" or "open with exclusive-create flag" operation.
- For in-memory state, confirm whether the check and the act acquire the
  *same* lock instance and whether that lock remains held continuously
  from before the check until after the act completes -- releasing and
  reacquiring the lock between them reintroduces the window even if both
  operations are individually "thread-safe."
- Add logging that records the value observed at check time and the value
  actually present at act time (before applying the action) in production
  or a load test; a mismatch under load directly confirms the race rather
  than requiring guesswork.

## Fix
Collapse the check and the act into a single atomic operation instead of
two separate steps, choosing the mechanism appropriate to where the state
lives:
- In-memory: hold one lock across both the check and the act as a single
  critical section, or better, use a primitive that performs the whole
  operation atomically (compare-and-swap, an atomic
  "insert-if-absent"/`putIfAbsent`-style map operation, or a monitor
  method that encapsulates both steps so callers can never observe or act
  between them).
- Databases: push the check into the same statement as the act using a
  unique constraint plus an upsert (`INSERT ... ON CONFLICT DO NOTHING`/
  `ON DUPLICATE KEY`/`MERGE`), a conditional update
  (`UPDATE ... WHERE balance >= amount`, checking the affected-row count
  rather than pre-reading the balance), or an explicit row lock
  (`SELECT ... FOR UPDATE`) held across both the check and the write
  within one transaction.
- Filesystems: use the atomic variant the OS provides for the exact intent
  -- exclusive-create open flags (`O_EXCL`) instead of stat-then-open,
  atomic rename for "publish this file" instead of check-then-write.
- Where no atomic primitive exists for the exact operation, invert the
  design from "check, then act" to "act, then verify the act succeeded as
  expected" (optimistic concurrency): perform the action unconditionally
  with a version/expected-state guard (e.g. compare-and-swap on a version
  number, conditional write with an `if-match` precondition) and treat a
  guard failure as the signal to retry or abort, rather than trusting a
  separate up-front check.

## Pitfalls
- Narrowing the race window by reordering statements or removing
  intervening code ("it's basically instant now") instead of making it
  atomic -- a smaller window is still a window, and it will still be hit
  under enough concurrency or load; this fix only make the bug rarer and
  harder to reproduce, not gone.
- Adding a lock around the check and a separate lock around the act,
  believing this to be sufficient, without holding one lock across both --
  this is one of the most common variants of this exact bug and passes
  casual code review because "everything has a lock on it."
- Solving it with a retry-after-failure loop around the unprotected
  check-then-act instead of an atomic operation -- this can mask the race
  in testing (the second attempt usually succeeds) while still allowing
  a rare double-action in production when both concurrent attempts
  succeed on their first try.

## Verify
Write a concurrency test that fires the operation from many
threads/workers simultaneously against the same shared state or record
(e.g. 100 concurrent "create if not exists" calls with the same key,
or 50 concurrent withdrawals racing the same balance down toward zero),
and assert the invariant that should never be violated (exactly one
record created, balance never goes negative) holds across many repeated
runs of the test, not just a single pass.
