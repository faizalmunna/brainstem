---
name: optimistic-locking-version-conflict-unhandled
description: Diagnose an entity update endpoint that throws an unhandled ObjectOptimisticLockingFailureException as a raw 500 error under concurrent edits instead of resolving the conflict gracefully.
triggers: ["objectoptimisticlockingfailureexception", "optimisticlockexception spring", "stale object state exception", "version conflict update entity", "concurrent edit 500 error jpa"]
permissions: ["READ"]
---

## Symptom
Two users (or two concurrent requests, e.g. a retry and the original)
update the same entity at nearly the same time, and one of them gets an
unhandled `ObjectOptimisticLockingFailureException` (wrapping
Hibernate's `StaleObjectStateException`) that propagates all the way up
to a generic 500 Internal Server Error with no meaningful message for
the client -- rather than either succeeding, or failing with a clear,
recoverable "someone else changed this, please refresh and retry"
response. It typically only appears under real concurrent usage or
double-click/retry scenarios, not in single-user manual testing.

## Likely causes
1. **The entity has an `@Version` field and no code anywhere catches
   `ObjectOptimisticLockingFailureException`** -- optimistic locking is
   working exactly as designed (correctly detecting that the row changed
   between load and save), but nothing translates that expected,
   recoverable condition into a sensible API response, so it falls
   through to the default exception handler as an unhandled error.
2. **A retry mechanism (client-side auto-retry, a message queue redelivery,
   an at-least-once job runner) resubmits the same update using a stale
   in-memory copy of the entity** after a partial failure, so the retry
   itself is the second writer racing against the first, and the version
   check correctly rejects it -- the "concurrency conflict" here is
   self-inflicted by the retry design, not two genuine independent users.
3. **The `@Version` field is being manually set or reset by application
   code** (e.g. a mapper that copies all fields from a DTO onto the
   entity including `version`, or a batch import path that constructs
   entities with a hardcoded version) -- this produces spurious version
   mismatches unrelated to real concurrent edits, and no amount of
   correct exception handling fixes the actual bug (the version field
   should never be set by application code).
4. **A long-running edit session (e.g. "load form, let user think, then
   submit") has a large enough window that conflicts are expected and
   common**, but the UI/API gives no indication to the user that their
   view might be stale, so every conflict surprises both the user and
   whoever is debugging the resulting error report.

## Diagnose
- Check the entity mapping for `@Version` and confirm it's a genuine
  optimistic-locking column (not a business "version" field reused for
  something else, which would explain conflicts unrelated to concurrency).
- Grep the codebase for any existing `catch` of
  `ObjectOptimisticLockingFailureException`,
  `OptimisticLockException`, or `StaleObjectStateException` -- their
  total absence confirms the conflict is currently unhandled anywhere in
  the stack.
- Reproduce deliberately: load the same entity in two separate
  transactions/sessions, modify and save the first, then modify and save
  the second using its now-stale in-memory copy -- confirm the second
  save throws the expected exception, and observe exactly what HTTP
  status/body the client currently receives for it.
- Check whether any mapper or DTO-to-entity conversion touches the
  `version` field explicitly -- if a mapping tool (MapStruct, manual
  setter calls, `BeanUtils.copyProperties`) copies a client-supplied or
  stale `version` value onto the managed entity, that's an independent
  bug to fix regardless of exception handling.

## Fix
Treat the version conflict as an expected, recoverable business
condition rather than an unexpected server error, and design a response
around what the client can actually do about it:
```java
@ExceptionHandler(ObjectOptimisticLockingFailureException.class)
ResponseEntity<ErrorBody> handleStaleUpdate(ObjectOptimisticLockingFailureException ex) {
    return ResponseEntity.status(HttpStatus.CONFLICT) // 409
        .body(new ErrorBody("RESOURCE_MODIFIED",
            "This record was changed by someone else; reload and retry."));
}
```
Map it to `409 Conflict` (not 500), and give the client enough
information to reload the current state and either retry the merge or
show the user what changed. For legitimate at-least-once retry paths
(queues, background jobs), re-fetch the current entity state before
retrying a failed operation instead of reusing the original stale copy,
so the retry naturally incorporates the winning write rather than racing
against it again. Never let application code set the `@Version` field
directly -- exclude it explicitly in any DTO-to-entity mapping
configuration.

## Pitfalls
- Silently swallowing the exception and re-saving with the current data
  ("last write wins" implemented as a workaround) defeats the entire
  purpose of optimistic locking and can silently discard the other
  writer's changes -- only do this deliberately, for fields genuinely
  safe to overwrite, never as a blanket catch-and-retry.
- Wrapping every save call in a generic retry-on-any-exception loop to
  "handle concurrency" also retries on unrelated failures (validation
  errors, constraint violations) that should never be retried, and can
  mask a real bug behind apparent flakiness -- catch specifically the
  optimistic-locking exception type, not `Exception` broadly.

## Verify
Add an integration test that loads the same entity twice into two
separate persistence contexts, saves the first successfully, then saves
the second and asserts the API returns `409 Conflict` with the expected
error body (not a 500) -- confirms both that the conflict is detected
and that it now surfaces as a handled, client-actionable response.
