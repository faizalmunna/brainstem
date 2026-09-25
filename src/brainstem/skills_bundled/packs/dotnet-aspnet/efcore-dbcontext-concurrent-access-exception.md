---
name: efcore-dbcontext-concurrent-access-exception
description: Diagnose intermittent EF Core exceptions caused by the same DbContext instance being used concurrently by more than one thread or request.
triggers: ["a second operation was started on this context", "dbcontext not thread safe error", "intermittent ef core exception under load", "concurrent use of context detected", "dbcontext instance was disposed"]
permissions: ["READ"]
---

## Symptom
The application intermittently throws
`InvalidOperationException: A second operation was started on this
context instance before a previous operation completed` or
`ObjectDisposedException` referencing a `DbContext`, usually only under
concurrent load and never reliably reproducible with a single manual
request. It often appears after adding `Task.WhenAll`/parallel
`await`s around multiple queries, or after introducing caching/static
fields that hold onto a context, or in background processing that fans
out work across threads.

## Likely causes
1. **The same `DbContext` instance is used to run multiple queries
   concurrently** -- e.g. `await Task.WhenAll(context.Set<A>().ToListAsync(),
   context.Set<B>().ToListAsync())` -- `DbContext` (and the underlying
   provider connection) is not thread-safe and doesn't support two
   in-flight operations on the same instance at once, even if each
   individual `await` looks correct in isolation.
2. **A `DbContext` is captured by a singleton, a static field, or a
   cached delegate/closure** and then reused across multiple concurrent
   requests -- each request thinks it owns a private context (because
   DI normally guarantees scoped-per-request), but the captured instance
   is actually shared, so concurrent requests race on it. This is a
   variant of the captive-dependency problem, surfacing as a threading
   exception rather than a stale-data one.
3. **A background job or `Parallel.ForEach`/manual `Task.Run` fan-out
   passes one injected `DbContext` into multiple parallel work items**
   instead of resolving a new scoped context per work item -- common
   when someone parallelizes a previously-sequential loop without
   realizing the context reference is shared across all the new tasks.
4. **The `DbContext` was disposed (end of a `using` block, or the DI
   scope ended) while an unawaited/fire-and-forget task from that scope
   is still running against it** -- e.g. code that kicks off a task and
   returns a response without awaiting, and the background task later
   touches a context whose owning request scope has already been disposed.

## Diagnose
- Grep for `Task.WhenAll`, `Parallel.ForEach`, `Task.Run`, or manual
  thread/task fan-out anywhere in the same method or call chain as
  `DbContext`/`context.Set<...>` usage -- any case where the same
  context variable is referenced inside more than one concurrently
  running task is a hit.
- Check the exception's stack trace for which two logical operations
  raced -- .NET's exception message and a captured stack (enable
  `EnableDetailedErrors()`/`EnableSensitiveDataLogging()` in a
  non-production diagnostic run) usually shows the second operation's
  call site, which points at the exact concurrent call.
- Search for any static field, singleton field, or long-lived closure
  typed as `DbContext`/a custom `AppDbContext` -- confirm nothing outside
  a properly scoped-per-request/per-job lifetime holds a reference.
- For fire-and-forget suspicion, grep for `Task.Run(...)` or unawaited
  async calls (`_ = SomeAsync()`) inside request handlers that reference
  `context` -- if the enclosing request can return before that task
  finishes, the scope (and its `DbContext`) may already be disposed when
  it runs.

## Fix
- Never share one `DbContext` instance across concurrent operations.
  Either run the operations sequentially against the same context
  (`await` one, then the other), or give each concurrent operation its
  own context instance (resolve a new one via `IDbContextFactory<T>` or a
  fresh DI scope) if they genuinely need to run in parallel.
- For genuinely parallel work (batch/background jobs), inject
  `IDbContextFactory<TContext>` and call `CreateDbContext()` per
  parallel unit of work instead of injecting a single scoped `DbContext`
  into code that fans out across threads.
- For fire-and-forget work that must outlive the request, don't reuse the
  request-scoped context -- create an explicit new `IServiceScopeFactory`
  scope for the background task with its own resolved `DbContext`, and
  make sure that scope's lifetime is tied to the background task, not the
  original request.

## Pitfalls
- Adding a manual lock (`lock`/`SemaphoreSlim`) around all `DbContext`
  usage to "make it thread-safe" avoids the exception but serializes all
  supposedly-parallel work through one context, throwing away the
  concurrency benefit that motivated the parallel code in the first place
  -- prefer giving each parallel path its own context via
  `IDbContextFactory` instead of synchronizing access to a shared one.
- Wrapping the operation in a try/catch that swallows the "second
  operation started" exception and retries hides a real correctness bug
  (the two operations may have partially executed against a corrupted
  connection state) rather than fixing the underlying concurrent-access
  issue -- treat the exception as a hard signal to fix the sharing, not
  noise to suppress.

## Verify
Reproduce under concurrent load (a load test hitting the affected
endpoint/job with realistic parallelism) and confirm the exception no
longer occurs after switching to per-operation contexts via
`IDbContextFactory` or sequential awaits, then run the same load test
several times to confirm the fix isn't just reducing the exception's
frequency but eliminating its root cause (no shared context reference
remains reachable from more than one concurrent path).
