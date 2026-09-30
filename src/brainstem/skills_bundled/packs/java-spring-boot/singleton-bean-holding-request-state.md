---
name: singleton-bean-holding-request-state
description: Diagnose data from one user's request leaking into another concurrent user's response because a singleton-scoped Spring bean stores per-request state in an instance field.
triggers: ["data leaking between users spring", "wrong user data returned under load", "singleton bean thread safety", "intermittent wrong data concurrent requests", "field shared across requests spring boot"]
permissions: ["READ"]
---

## Symptom
Under concurrent traffic, one user occasionally receives data that
belongs to a *different* user -- a name, an ID, a computed total, or an
authorization decision that doesn't match who's actually logged in. It's
intermittent and load-dependent: it doesn't reproduce with one request
at a time, only shows up under real concurrency, and often first appears
in production or load testing rather than in development. The class
responsible is a normal `@Service`/`@Component` (default singleton
scope) that stores something in a plain instance field and reads it back
later in the same request-handling flow.

## Likely causes
1. **A mutable instance field on a singleton bean is set at the start of
   a request-handling method and read later in the same call chain** --
   e.g. `this.currentUser = ...` set in one method, read in another
   method on the same bean instance. Because Spring singletons are one
   shared instance across all threads, two requests interleaving on
   different threads race on that field, and one overwrites the other's
   value before it's read.
2. **A field intended as a per-request cache/accumulator** (a list being
   built up, a running total, a "current request context" object) is
   declared on the singleton instead of scoped correctly, often
   introduced by someone refactoring a method's local variable into a
   field for convenience (e.g. to avoid passing it through several
   private method calls) without realizing the scope implication.
3. **A `SimpleDateFormat`, `Calendar`, or similar known-non-thread-safe
   JDK utility is stored as a singleton bean field** and reused across
   concurrent calls -- a narrower but very common variant of the same
   root pattern, producing corrupted/wrong values rather than an
   obvious crash.
4. **A request-scoped or session-scoped bean was intended but the scope
   annotation is missing or misapplied** -- e.g. `@RequestScope` left
   off a bean that legitimately needs per-request state, so Spring
   defaults it to singleton without any error or warning.

## Diagnose
- Grep the suspect bean class for mutable (non-`final`) instance fields
  that are assigned inside a method rather than only in the constructor
  or via `@Autowired` -- any field written after construction on a
  default-scoped bean is a candidate.
- Confirm the bean's scope: absence of `@RequestScope`/`@SessionScope`/
  `@Scope("prototype")` means singleton by default -- check there's no
  scope annotation actually present that would rule this out.
- Reproduce under real concurrency, not sequential requests: fire two
  concurrent requests as two different simulated users (a load test
  tool, or two threads in an integration test) and assert that each
  response contains only its own user's data -- sequential manual
  testing will not surface a race condition.
- If already in production, correlate incident timing with load
  (concurrent request count) -- a reproduction rate that increases with
  concurrency and decreases with low traffic strongly implicates a
  shared-mutable-state race over a purely logical bug.

## Fix
Move per-request state out of the singleton entirely, matching state
lifetime to the actual scope it needs:
- Pass the value as a method parameter or return value through the call
  chain instead of stashing it in a field -- this is almost always
  possible and is the cleanest fix because it makes the data flow
  explicit and removes the shared mutable state altogether.
- Where threading it through many method signatures is genuinely
  impractical, use a proper Spring `@RequestScope` bean (a real
  per-request-scoped object, safely proxied by Spring) to hold that
  state, or use a `ThreadLocal` scoped and cleared correctly for the
  duration of the request (with a guarantee it's cleared in a `finally`
  block or a `HandlerInterceptor.afterCompletion`, since thread-pool
  reuse means a `ThreadLocal` not cleared leaks into the *next* request
  handled by that thread).
- For known non-thread-safe JDK utilities, replace them with their
  thread-safe equivalents (`DateTimeFormatter` instead of
  `SimpleDateFormat`) or construct a new instance per use instead of
  storing one on the singleton.

## Pitfalls
- Adding `synchronized` around the field access "fixes" the race but
  serializes all requests through that bean, turning a correctness bug
  into a throughput bottleneck -- treat it as a stopgap at best, since
  the actual bug is state that shouldn't be shared in the first place,
  not a missing lock.
- Introducing a `ThreadLocal` without a guaranteed cleanup path is a
  common "fix" that trades an obvious cross-user leak for a subtler one:
  under a thread pool, a value set for request A and never cleared can
  be read by request B if B happens to be handled by the same pooled
  thread later -- always pair `ThreadLocal.set()` with a `remove()` in a
  `finally`/interceptor-completion hook.

## Verify
Write a concurrency test that fires N concurrent requests (N >= 10)
impersonating N distinct users through the actual web layer (not calling
the service method directly in a single thread), and assert each
response's user-identifying field matches the request that produced it
-- run it repeatedly (race conditions are probabilistic) and confirm
zero cross-user mismatches across multiple runs, not just one clean run.
