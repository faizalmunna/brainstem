---
name: transactional-checked-exception-no-rollback
description: Diagnose a @Transactional method that commits partial writes instead of rolling back when it throws a checked exception.
triggers: ["transaction did not roll back", "checked exception did not trigger rollback", "data committed after exception was thrown", "rollbackfor not working", "partial writes after failure"]
permissions: ["READ"]
---

## Symptom
A `@Transactional` method throws an exception partway through, and the
team expects the transaction to roll back -- but instead, rows written
earlier in the method are committed to the database, leaving the system
in a half-completed state. Logs show the exception was thrown and caught
somewhere up the stack, yet the data changes made before the throw
persist. This is distinct from self-invocation bugs: the transaction
*is* active (it can be confirmed via `TransactionSynchronizationManager`),
it simply doesn't roll back on this particular exception.

## Likely causes
1. **The thrown exception is a checked exception**, and Spring's default
   rollback rule only rolls back on `RuntimeException` and `Error` --
   checked exceptions commit by default unless `rollbackFor` is
   explicitly configured. Wrapping a checked `IOException` or a custom
   checked business exception and letting it propagate out of a
   `@Transactional` method is the single most common cause of this bug.
2. **The exception is caught and swallowed (or logged and suppressed)
   inside the transactional method itself**, so it never propagates out
   to the proxy's advice at all -- from Spring's perspective the method
   returned normally, so it commits, regardless of `rollbackFor` settings.
3. **`noRollbackFor` is set (intentionally or by a copy-pasted annotation)
   for the specific exception type being thrown**, silently overriding
   what looks like a sensible default.
4. **The exception is thrown from an asynchronous or separately-transacted
   piece of work** (a `@Async` method, a separate thread, an event
   listener with its own propagation) that runs outside the original
   transaction's boundary, so the original transaction has nothing to
   roll back to react to.

## Diagnose
- Identify the exact exception class thrown and check whether it extends
  `RuntimeException`/`Error` or `Exception` directly (checked). This one
  check resolves the majority of cases immediately.
- Grep the method and its `@Transactional` annotation for `rollbackFor`
  and `noRollbackFor` attributes, and check any class-level
  `@Transactional` defaults it might be inheriting.
- Search the method body (and everything it calls within the same
  transaction) for a `try/catch` that swallows the exception or converts
  it to a return value/status code instead of letting it propagate.
- Enable transaction debug logging
  (`logging.level.org.springframework.transaction=DEBUG`) and re-run the
  failing case -- it logs whether a rollback was actually initiated,
  distinguishing "rollback attempted but something else committed
  anyway" from "rollback was never triggered."

## Fix
Make the rollback trigger explicit rather than relying on the default
rule, since the default (`RuntimeException`/`Error` only) is a common
source of surprise for teams using checked exceptions for business
errors:
```java
@Transactional(rollbackFor = Exception.class)
void placeOrder(Order o) throws InventoryException {
    ...
    if (insufficientStock) {
        throw new InventoryException("out of stock"); // checked
    }
}
```
If the codebase deliberately uses checked exceptions for expected
business failures, standardize on always declaring `rollbackFor`
wherever a checked exception can escape a transactional method --
or, more robustly, convert business-rule failures to a dedicated
unchecked exception hierarchy so the default rollback rule does the
right thing without per-method configuration. If the real cause is a
swallowed exception, the fix is to stop swallowing it inside the
transactional boundary, or to explicitly call
`TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`
before deciding to continue processing.

## Pitfalls
- Blanket-applying `rollbackFor = Exception.class` everywhere without
  thinking about it can mask a deeper design smell (using exceptions,
  checked or not, for expected/recoverable conditions inside a hot path)
  -- prefer distinguishing "should roll back the transaction" from
  "should be reported to the caller" explicitly rather than reflexively
  widening rollback rules.
- Calling `setRollbackOnly()` and then continuing to execute more writes
  in the same transaction is a common follow-on mistake: the transaction
  is now marked rollback-only, so those later writes appear to succeed at
  the call site but silently never commit, and the eventual commit
  attempt throws `UnexpectedRollbackException` -- treat rollback-only as
  terminal for that transaction, not as a warning flag to keep working
  around.

## Verify
Write an integration test that calls the transactional method with input
engineered to throw the specific checked exception after at least one
write has occurred, then query the database directly (not through the
same persistence context/cache) to confirm none of the method's writes
are present -- this fails (shows committed partial data) before adding
`rollbackFor` and passes after.
