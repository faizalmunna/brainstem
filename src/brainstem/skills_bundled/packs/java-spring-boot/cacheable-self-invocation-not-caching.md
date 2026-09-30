---
name: cacheable-self-invocation-not-caching
description: Diagnose a @Cacheable method that runs its expensive body every single call because it was invoked from another method on the same bean.
triggers: ["cacheable not working", "cache annotation ignored spring", "method still executing despite cacheable", "spring cache proxy self call", "cache never hits same class"]
permissions: ["READ"]
---

## Symptom
A method annotated `@Cacheable` still executes its full body (a slow
query, an external API call, an expensive computation) on every
invocation, never serving a cached result -- confirmed by adding a log
line at the top of the method and seeing it fire every time, including
with identical cache-key arguments. Calling the same method through a
different bean (e.g. from a controller that injects the service) caches
correctly; the failure is specific to calling it from *within another
method of the same class*.

## Likely causes
1. **Self-invocation bypasses the caching proxy**, the same underlying
   AOP-proxy limitation that breaks `@Transactional` self-invocation:
   Spring's default caching support is also proxy-based, so a call made
   via `this.getData()` or a bare `getData()` from another method in the
   same class never passes through the proxy that implements cache
   lookup/population, and the annotation is silently a no-op for that
   call path. This is a distinct mechanism from a cache-key or
   configuration bug and needs a structural fix, not a cache-config
   tweak.
2. **No `CacheManager`/cache is actually configured**, so `@Cacheable`
   resolves to a no-op cache (or throws, depending on Spring Boot
   version and auto-configuration) -- this produces a similar-looking
   "never caches" symptom but affects *all* call paths, not just
   self-invocation, which is the key distinguishing diagnostic fact.
3. **The cache key varies unexpectedly between calls that look
   identical** -- e.g. the method's argument is an object without a
   proper `equals()`/`hashCode()`, or a `key`/`keyGenerator` SpEL
   expression includes a field that differs per call (a timestamp, a
   freshly-created object reference) -- producing cache misses that look
   like caching "isn't working" but are actually correct behavior for a
   key that's never really the same twice.
4. **The method is called with `sync = false` (default) under high
   concurrency**, and many concurrent calls with the same key all miss
   before the first result is cached (a thundering-herd effect) --
   caching *is* working, but looks broken under load-test conditions
   because most concurrent calls compute independently before the first
   population completes.

## Diagnose
- Confirm whether the no-caching behavior is universal or specific to
  same-class calls: call the `@Cacheable` method from a *different* bean
  (inject the service elsewhere and call it) and check whether that path
  caches correctly -- if it does, this narrows straight to self-
  invocation, ruling out causes 2 and 3.
- If it fails even from outside the class, check that a `CacheManager`
  bean actually exists and is backed by a real store: log
  `cacheManager.getCacheNames()` at startup and confirm the target cache
  name is present and not silently a `NoOpCacheManager` (Spring Boot
  auto-configures a no-op cache manager if no caching library is on the
  classpath and no explicit provider is configured).
- Log the resolved cache key on each call (or use
  `@Cacheable(... condition = ...)` temporarily with a logging aspect)
  and compare keys across calls that are expected to hit -- if the keys
  differ when they shouldn't, that's a key-generation problem, not a
  proxy problem.
- Grep the class for calls to its own `@Cacheable` methods (`this.` or
  bare method calls) to confirm the self-invocation call path exists at
  all before assuming that's the cause.

## Fix
Route the call through the proxy, exactly as with the analogous
`@Transactional` self-invocation problem: extract the `@Cacheable`
method into a separate collaborator bean and call it through an injected
reference, rather than calling it on `this`:
```java
@Service
class ReportService {
    private final PricingLookup pricingLookup; // separate bean
    Report build(Order o) {
        var price = pricingLookup.currentPrice(o.getSku()); // via proxy
        ...
    }
}
@Service
class PricingLookup {
    @Cacheable("prices")
    BigDecimal currentPrice(String sku) { ... }
}
```
If the "no caching at all" cause is a missing/no-op `CacheManager`,
explicitly configure a real cache provider (Caffeine, Redis, etc.) and
confirm `@EnableCaching` is present on a configuration class. If the
cause is key instability, define an explicit `key` SpEL expression (or
a custom `KeyGenerator`) built only from the arguments that genuinely
identify a cacheable unit of work, not from freshly-allocated or
mutable objects.

## Pitfalls
- Don't conflate this with the `@Transactional` self-invocation skill's
  fix and assume moving *all* annotated methods into one shared
  "proxy-bait" utility class is good design -- extract collaborators
  along real domain boundaries; a grab-bag class of "things that needed
  a proxy" becomes its own maintenance problem.
- Adding `sync = true` to fix a thundering-herd miss under concurrency
  changes the caching semantics (only one thread computes, others block
  waiting) -- appropriate for genuinely expensive, idempotent
  computations, but a poor default for cheap methods where blocking
  concurrent callers costs more than the occasional duplicate
  computation would.

## Verify
Add a call counter (or a log line) inside the cached method's body, call
it multiple times with the same arguments through the *actual* call path
that was failing (i.e. from the same-class caller, not directly from a
test), and confirm the counter increments only once per distinct
argument set after the fix, versus once per call before it.
