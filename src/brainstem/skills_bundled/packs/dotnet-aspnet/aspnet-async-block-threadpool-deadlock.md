---
name: aspnet-async-block-threadpool-deadlock
description: Diagnose an ASP.NET request that hangs indefinitely or times out because code blocks on an async call with .Result or .Wait() instead of awaiting it.
triggers: ["request hangs forever aspnet", "deadlock calling .Result on task", "async method never completes", ".Wait() hangs asp.net", "controller action times out under load"]
permissions: ["READ"]
---

## Symptom
A specific request handler (controller action, Razor Page handler, or a
method called from one) hangs forever or times out with no exception,
where the code path calls `.Result`, `.Wait()`, or `.GetAwaiter().GetResult()`
on a `Task` instead of awaiting it. In ASP.NET Framework/classic MVC this
produces a textbook deadlock on the request's `SynchronizationContext`. In
ASP.NET Core (no `SynchronizationContext` by default) the same pattern
doesn't deadlock the same way but instead causes intermittent hangs and
timeouts under load as it starves the thread pool -- both are the same
root anti-pattern showing up differently by hosting model.

## Likely causes
1. **Synchronous-over-asynchronous blocking on a captured context**
   (ASP.NET Framework/classic MVC, or any code still running under a
   non-default `SynchronizationContext`) -- the awaited continuation
   inside the called async method needs to resume on the captured
   context, but that context's single thread is the one blocked waiting
   on `.Result`, so neither side can proceed. Classic deadlock.
2. **Thread-pool starvation in ASP.NET Core** -- there's no
   `SynchronizationContext` to deadlock on, but every blocked thread
   sits idle holding a thread-pool thread while the async work it's
   waiting on needs a thread-pool thread to run its continuation; under
   enough concurrent load the pool can't grow fast enough (thread-pool
   injection is throttled) and requests queue up and time out, looking
   like an intermittent hang rather than a hard deadlock.
3. **A library method that is `async` internally but exposes only a
   synchronous public API**, so a caller who wants "just call it and
   wait" reaches for `.Result`/`.Wait()` because there's no async
   overload to await -- often introduced through a legacy SDK or a
   third-party package wrapper.
4. **Mixing `async void` or fire-and-forget calls with a synchronous
   wait added later "just to be safe"** by someone who saw an unawaited
   warning and blocked on the task instead of propagating `async`/`await`
   up the call chain, spreading the anti-pattern rather than fixing it.

## Diagnose
- Grep the codebase for `.Result`, `.Wait(`, and `.GetAwaiter().GetResult()`
  on `Task`/`Task<T>` types -- every hit is a blocking-on-async call and a
  candidate cause; cross-reference which ones sit on a request-handling
  path.
- If on ASP.NET Framework/classic MVC: capture a memory dump of a hung
  process (or attach a debugger) during the hang and inspect the thread
  pool -- a deadlock shows exactly one thread blocked in the blocking call
  and the continuation thread waiting to enter the same
  `SynchronizationContext`, with `!syncblk`/parallel-stacks showing the
  circular wait.
- If on ASP.NET Core: check thread-pool health during the incident window
  (`ThreadPool.GetAvailableThreads` logged periodically, or the
  `.NET Thread Pool` EventCounters/`dotnet-counters monitor`) -- a rising
  queue length and rising "thread pool completed items rate" lag alongside
  growing request latency points to starvation, not a single deadlocked
  request.
- Confirm causation by removing/awaiting the blocking call in a staging
  environment under the same load profile and checking whether the hang
  or timeout pattern disappears.

## Fix
- Make the call chain `async` end-to-end: change the blocking caller to
  an `async` method and `await` the call instead of blocking on it, then
  propagate `async`/`await` up through every caller until it reaches a
  framework-supported async entry point (controller actions and
  middleware in both ASP.NET Framework and Core support `async Task`
  return types).
- Where a truly synchronous boundary is unavoidable (e.g. a constructor,
  or a third-party interface that mandates a sync method), prefer running
  the async work through a mechanism that doesn't reuse the same
  request/UI context -- e.g. offloading to `Task.Run` and blocking on
  *that* wrapper task from a non-context-sensitive thread -- but treat
  this as a last resort, not the fix, since it still consumes a thread
  for the duration.
- For library code you own, expose only async APIs on I/O-bound paths
  rather than a sync wrapper that internally blocks -- that sync wrapper
  is exactly the trap the next caller falls into.

## Pitfalls
- Reaching for `ConfigureAwait(false)` on every awaited call as a blanket
  "fix" for deadlocks papers over the real problem (a sync-over-async
  call still in the chain) and can itself introduce bugs if code after
  the `await` actually needs the original context (e.g. HttpContext
  access in classic ASP.NET) -- fix the blocking call, don't just suppress
  the context capture around it.
- Converting only the outermost method to `async` while an inner helper
  still calls `.Result` doesn't fix anything -- the deadlock/starvation
  risk lives at the point of the blocking call, not the caller's
  signature; verify every level of the chain is actually awaiting, not
  just declared `async`.

## Verify
Reproduce the original hang under a load test that mirrors production
concurrency (not a single manual request, since thread-pool starvation
specifically needs concurrent load to manifest), confirm it hangs/times
out on the current code, then confirm the same load test completes all
requests with stable latency once every `.Result`/`.Wait()` on the path
is replaced with `await`.
