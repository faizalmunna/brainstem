---
name: pooled-thread-leaks-state-between-unrelated-requests
description: Diagnose data from one request appearing in an unrelated later request because thread-local state was assumed to be per-request but the underlying thread was reused from a pool.
triggers: ["wrong user data showing up in another users request", "thread local leaking between requests", "stale data from previous request", "intermittent cross request contamination", "request context bleeding into next request"]
permissions: ["READ"]
---

## Symptom
A value that should be scoped to a single request or task -- a user ID,
a tenant/organization ID, a security context, a locale, a database
transaction handle, a trace/correlation ID -- occasionally shows up
attached to a completely unrelated later request, as if two requests'
contexts got merged. It's intermittent, worse under load (when the thread
pool is actually being reused rapidly rather than sitting mostly idle
with fresh threads), and often first noticed as a serious-looking bug
(one user briefly seeing another user's data) that then turns out to
trace back to a thread-local variable rather than any shared mutable
object.

## Likely causes
1. **Thread-local storage is set at the start of request handling but
   never cleared at the end** -- the framework or application code calls
   something like `threadLocal.set(requestContext)` when a request comes
   in, but relies on garbage collection or "it'll be overwritten next
   time" instead of explicitly clearing it in a `finally`/`ensure` block;
   when the *next* request on that same pooled thread sets a *different*
   value, this works by luck, but if the next request path forgets to
   set it at all (an unauthenticated route, a background callback, an
   error-handling path that runs before context is normally established),
   it reads the previous request's leftover value.
2. **The thread pool outlives the assumption that "thread equals request"
   built into the code** -- code was written assuming a fresh thread per
   request (true for old thread-per-request server models) but the
   application now runs on a reused worker/executor pool, an async
   runtime that multiplexes many logical tasks onto few OS threads, or a
   virtual-thread/green-thread model where the mapping from thread to
   request is no longer 1:1 at all -- the thread-local mechanism itself
   is still "correct" but the mental model of what it scopes has become
   wrong.
3. **An async/callback boundary hops execution onto a different thread (or
   back onto a reused one) mid-request**, and code re-reads a thread-local
   after that hop expecting it to still reflect the original request's
   context -- in many async runtimes, thread-locals do not automatically
   propagate across an async continuation the way they would across a
   plain synchronous call stack, so the value read after the hop can be
   either empty or, worse, whatever the executing thread's pool slot was
   last used for.
4. **A caching or connection-pooling layer keyed loosely by thread
   identity** (rather than by request or session) reuses a
   thread-affinitized resource -- e.g. a database connection or
   transaction stashed in a thread-local "for convenience" -- and a
   later, unrelated request on that same thread picks up the previous
   request's still-open connection or transaction state.

## Diagnose
- Confirm the runtime's threading/pooling model first: is this a
  thread-per-request server, a fixed-size worker pool, an async
  event-loop-plus-executor hybrid, or a virtual-thread scheduler? This
  determines whether "thread reuse" is even possible and how often --
  check the pool configuration (min/max pool size, whether threads are
  recycled after N requests) directly rather than assuming.
  the framework's documented behavior for what does and doesn't survive
  an async continuation.
- Grep for every `set` call on the suspect thread-local (or
  equivalent: a language's thread-local storage API, an
  `AsyncLocal`/context-var/context-local abstraction) and verify each one
  has a matching `clear`/`remove` in a `finally`/`ensure`/`defer` block
  that runs on every exit path, including exceptions and early returns --
  not just the happy path.
- Reproduce by adding a log line that prints the thread ID alongside the
  thread-local's value at both the start and end of request handling,
  then drive load through the same pool size the bug was reported under;
  look for a case where a thread ID repeats across two different
  requests' logs with an unexpected value carried over.
- For async runtimes, check specifically whether the language/framework's
  context-propagation mechanism (a context-var, `AsyncLocal`, structured
  concurrency's scoped context) is being used instead of a raw
  thread-local -- raw thread-locals are the most common single point of
  failure here because they follow the OS/runtime thread, not the logical
  task, across an async hop.

## Fix
Make request-scoped state explicitly tied to the request's lifecycle
rather than implicitly tied to whichever thread happens to execute it:
- Always clear thread-local state in a `finally`/`ensure`/`defer` block
  immediately after request handling completes, on every exit path
  including exceptions, so a thread returning to the pool never carries
  state forward regardless of what the next request on it does or
  doesn't set.
- Where the runtime provides a request/task-scoped context propagation
  mechanism designed to survive async hops correctly (context variables,
  `AsyncLocal`, a structured-concurrency scope, a framework's built-in
  request-context abstraction), use that instead of a raw thread-local --
  these are specifically built to follow the logical unit of work rather
  than the underlying OS thread.
- Prefer passing request context explicitly as a parameter through the
  call chain over implicit thread-bound state wherever the codebase's
  size and call-chain depth make that tractable -- this eliminates the
  entire class of bug by construction, at the cost of more verbose
  function signatures, and is worth it specifically for
  security-sensitive context like user/tenant identity.
- For pooled resources stashed per-thread for convenience (connections,
  transactions), scope them explicitly to the request/transaction
  boundary with an explicit acquire-at-start, release-at-end pattern
  (ideally via the language's resource-scoping construct --
  try-with-resources, `using`, a context manager) rather than a
  thread-local cache that outlives any single request's ownership of it.

## Pitfalls
- Clearing the thread-local only on the successful/happy-path exit and
  missing exception paths -- an exception thrown mid-request skips a
  plain end-of-method cleanup line, leaving the previous value in place
  for the next request on that thread; the cleanup must be in a
  `finally`/`ensure`/`defer` construct that runs unconditionally.
- Assuming a context-propagation mechanism marketed as "async-safe"
  automatically covers every async pattern in use -- some only propagate
  correctly across the specific async primitives the framework itself
  controls (its own task scheduler) and not across manually-created
  threads, third-party callback registrations, or fire-and-forget
  background work spawned without using that mechanism.
- Fixing the immediate reported leak (e.g. clearing one specific
  thread-local) without auditing for other thread-locals or
  thread-affinitized caches in the same codebase -- this bug class tends
  to be systemic once a codebase has one instance, since the same
  "set without guaranteed clear" pattern is usually copy-pasted or
  independently reinvented elsewhere.

## Verify
Run a load test that cycles many distinct simulated requests (each with
a distinguishable identity, e.g. a unique tenant ID) through a
small, fixed-size thread/worker pool at high enough throughput that
thread reuse is guaranteed within the test's duration, and assert that
every response's context matches the request that produced it with zero
cross-contamination across thousands of cycles. Additionally, run the
same test with a deliberately-injected exception on a fraction of
requests to confirm cleanup still happens correctly on error paths, not
only the happy path.
