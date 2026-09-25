---
name: transactional-self-invocation-no-effect
description: Diagnose a @Transactional method whose transaction silently never starts because it was called from another method on the same bean instance.
triggers: ["transactional not working", "changes not rolling back", "self invocation transaction", "transactional annotation ignored", "no transaction active when i call another method"]
permissions: ["READ"]
---

## Symptom
A method annotated `@Transactional` runs without error, but no
transaction is actually active while it executes: writes that should be
grouped atomically commit individually, a deliberate exception thrown to
test rollback doesn't roll anything back, and `TransactionSynchronizationManager.isActualTransactionActive()`
returns `false` when checked from inside the method. The annotation is
present, spelled correctly, and the class is a Spring-managed bean --
yet it behaves as if `@Transactional` weren't there at all. Critically,
this only happens when the method is called from *another method in the
same class*, not when called from a different bean.

## Likely causes
1. **Self-invocation through the proxy is bypassed** -- Spring's default
   `@Transactional` support is proxy-based (JDK dynamic proxy or CGLIB).
   The proxy wraps the bean and intercepts calls made *from outside* the
   bean. A call made via `this.otherMethod()` from inside the same class
   goes directly to the real object, never passing through the proxy, so
   none of the transactional advice runs.
2. **The method is `private` or `final`** -- even when called from
   outside, CGLIB proxies (used for classes without interfaces) cannot
   override `private` or `final` methods, so the advice silently never
   applies regardless of invocation path.
3. **`@Transactional` is on a class that isn't actually a Spring bean**,
   or the class is excluded from component scanning -- less common, but
   produces the identical externally-visible symptom (no transaction,
   no error) and should be ruled out first before assuming self-invocation.
4. **AspectJ compile-time/load-time weaving isn't actually configured**
   despite believing it is -- if someone previously "fixed" a similar bug
   by adding `@EnableAspectJAutoProxy(proxyTargetClass=true)`, that still
   doesn't enable AspectJ weaving; it only switches JDK-proxy to
   CGLIB-proxy, which still doesn't fix self-invocation.

## Diagnose
- Confirm proxy-based AOP is in play: check for `spring-boot-starter-aop`
  and the absence of AspectJ load-time/compile-time weaving configuration
  (`ajc`, `-javaagent:aspectjweaver`). If no weaving is configured, it's
  proxy-based, and self-invocation is the prime suspect.
- Reproduce with a log line or breakpoint inside the inner method printing
  `TransactionSynchronizationManager.isActualTransactionActive()` --
  `false` confirms no transaction is active despite the annotation.
- Check the call site: is the transactional method invoked as
  `this.someMethod()` (or bare `someMethod()`) from another method in the
  *same class*, versus injected as a bean and called through its Spring
  proxy? Grep the class for calls to its own `@Transactional` methods.
- Check the method modifier -- `private` or `final` on a CGLIB-proxied
  bean explains the symptom even for externally-invoked calls, which is
  a different root cause than self-invocation and needs a different fix.

## Fix
Restructure so the transactional method is always called *through the
Spring proxy*, not directly on `this`. The standard pattern is to move
the transactional method into a separate collaborator bean and inject
that bean, then call it from the outer method:
```java
@Service
class OrderService {
    private final OrderPaymentTx paymentTx; // separate bean, injected
    void placeOrder(Order o) {
        paymentTx.chargeAndSave(o); // goes through paymentTx's proxy
    }
}
@Service
class OrderPaymentTx {
    @Transactional
    void chargeAndSave(Order o) { ... }
}
```
If splitting the class isn't practical, self-injection works but is
uglier and easy to get wrong with circular-dependency startup ordering:
inject `ApplicationContext` or a `@Lazy` self-reference and call the
method through that proxy instead of `this`. Whichever approach is used,
the underlying reasoning is the same: transactional advice only fires
when the call passes through the bean's proxy, so the fix is always
"route the call through the proxy," not "make the annotation work
harder."

## Pitfalls
- Self-injecting `@Autowired private OrderService self;` in the same
  class without `@Lazy` can cause a circular-dependency-like startup
  failure or return the raw (non-proxied) bean depending on Spring
  version and proxy mode -- prefer extracting a real collaborator bean,
  which is unambiguous and testable in isolation.
- Switching to AspectJ weaving to "fix" self-invocation properly works
  but changes build tooling (needs `ajc` or the aspectj Maven/Gradle
  plugin) and is a much bigger change than most teams intend to make for
  one bug -- reserve it for cases where restructuring calls genuinely
  isn't feasible.

## Verify
Add an integration test that calls the outer (non-transactional) method,
have the extracted transactional collaborator throw a `RuntimeException`
partway through its writes, and assert that none of its writes are
visible afterward (rollback occurred) -- this fails before the fix
(partial writes commit) and passes after it.
