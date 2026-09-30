---
name: distributed-transaction-partial-commit-no-recovery
description: A two-phase commit or saga fails partway through and leaves the system in a partially committed state with no automated compensation.
triggers: ["saga stuck halfway", "two phase commit failed partway", "partial commit across services", "distributed transaction left inconsistent state"]
permissions: ["READ"]
---

## Symptom

A business operation that spans multiple services or data stores
(charge a payment, reserve inventory, create a shipment; or a 2PC
transaction across multiple database shards) fails partway through
execution -- one or more steps succeeded and were never rolled back,
while a later step failed or the coordinating process crashed. The
result is a customer charged with no order created, inventory
decremented with no corresponding sale, or a multi-shard transaction
where some participants committed and others didn't. There's no
automated process undoing the completed steps, so the inconsistency
sits there until someone notices (a support ticket, a reconciliation
report) and fixes it by hand.

## Likely causes

- **The saga/transaction was designed with forward steps but no
  corresponding compensating actions**, or compensations exist for
  some steps but not all -- often because the steps added later
  (a new "send confirmation email" or "update analytics" step) were
  never given a compensation when the original saga was designed.
- **The coordinator (the process orchestrating the saga, or the
  transaction manager in 2PC) crashed or lost its state mid-
  transaction**, and there's no durable record of which steps had
  completed, so on restart there's nothing to resume or compensate
  from -- the in-flight transaction's progress was only ever held in
  memory.
- **A compensating action itself can fail** (the refund API is down,
  the inventory-release call times out), and the system has no retry-
  with-backoff or dead-letter handling for compensations specifically,
  treating "issue the compensation" as a fire-and-forget call rather
  than an operation that itself needs the same reliability guarantees
  as the forward steps.
- **Steps in the saga aren't idempotent**, so a naive "just retry the
  whole saga from the start" recovery approach risks re-running
  already-completed steps (double charge, double shipment) instead of
  safely resuming only the failed step.

## Diagnose

1. Find the specific incident's saga/transaction ID in logs or a saga-
   state table and reconstruct exactly which steps executed
   successfully, which failed, and what (if anything) the
   orchestrator attempted afterward.
2. Check whether a durable saga-state record exists at all (a
   database row tracking "step 2 of 4 complete") versus the
   orchestration being purely in-process/in-memory -- the latter means
   any coordinator crash is unrecoverable by design.
3. For each step involved, check whether a compensating action is
   defined in code at all, and if so, check its own error handling --
   does it retry, alert, or silently swallow failures?
4. Check idempotency of each forward step and each compensation
   independently (can each safely be invoked twice), since recovery
   design depends heavily on this.
5. Query for other transactions in the same stuck/partial state
   (not just the one that triggered the investigation) to size the
   actual blast radius -- this failure mode is rarely a true one-off.

## Fix

Persist saga state durably at each step transition (a saga-state
table recording which step is in progress or complete) before
executing that step's side effect, so a crashed orchestrator can be
restarted by a recovery process that reads the last known state and
resumes forward or begins compensating from exactly that point --
never by re-running the whole saga blind. Define a compensating
action for every forward step at design time, not added reactively
after an incident, and give compensations the same reliability
treatment as forward actions: retries with backoff, a dead-letter
queue for compensations that keep failing, and alerting when a
compensation has been retrying beyond a threshold. Make every step and
every compensation idempotent (keyed by the saga/transaction ID) so
the recovery process can safely retry without causing new duplicate
side effects. For true 2PC across data stores, prefer a transaction
manager that persists the prepare/commit decision durably and reliably
drives participants to a consistent outcome after a crash, or
consider whether the use case can be redesigned as a saga with
compensations instead, since 2PC's blocking behavior under coordinator
failure is itself a significant availability risk.

## Pitfalls

Don't rely on "we'll notice from customer complaints or reconciliation
reports" as the actual recovery mechanism -- that's a manual process
disguised as a plan, and it scales badly and erodes trust each time
it happens. Also don't add compensations without making them
idempotent and retryable themselves -- a compensation that fires once,
fails, and is never retried leaves the exact same partial-state
problem it was meant to solve, just one layer deeper.

## Verify

Inject a failure at each individual step of the saga in a test
environment (kill the process, force a downstream call to fail) and
confirm that either the saga completes via retry or every already-
completed step is fully compensated, with no manual intervention.
Separately, run a reconciliation query across the relevant systems
(payments vs. orders vs. inventory) after a batch of chaos-injected
failures and confirm zero mismatched records remain uncompensated
after the automated recovery window has passed.
