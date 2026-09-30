---
name: mockito-verify-flaky-async-invocation-count
description: A verify() call asserting an exact invocation count fails intermittently because the code under test dispatches work to another thread asynchronously.
triggers: ["verify times fails intermittently", "flaky Mockito verify async", "WantedButNotInvoked flaky test", "TooFewActualInvocations sometimes passes"]
permissions: ["READ"]
---

## Symptom
`verify(auditLogger, times(1)).log(any());` fails maybe 1 in 10 runs with `WantedButNotInvoked` or `TooFewActualInvocations`, even though manual testing shows the log call clearly happens. It's often worse in CI than locally, and re-running the exact same test frequently makes it pass.

## Likely causes
1. **The code under test hands work to an `ExecutorService`, `CompletableFuture.runAsync`, `@Async` Spring method, or a message listener thread**, and the test's `verify()` runs on the main test thread immediately after calling the method under test -- before the background thread has actually executed the mocked call. This is a genuine race, not mock misconfiguration.
2. **The test relies on a fixed `Thread.sleep(200)` "to be safe"** before verifying, which works most of the time locally but is too short under CI load (shared runners, thread contention) where the async task takes longer to schedule.
3. **An executor/thread pool isn't being shut down or awaited between tests**, so a slow previous test's async task completes *during* a later test and increments an invocation count the later test didn't expect, producing `TooManyActualInvocations` instead.
4. **The production code silently swallows an exception in the async path** (e.g. a bare `catch (Exception e) {}` inside a `Runnable`), so the mocked call sometimes never executes at all due to an unrelated bug, and the flaky test is actually surfacing a real intermittent failure in production code, not a test-only timing issue.

## Diagnose
1. Confirm asynchrony first: search the method under test for `ExecutorService`, `CompletableFuture`, `@Async`, `Thread`, or a message queue listener. If none of these exist, the flakiness has a different cause (e.g. shared mock state) -- don't assume async without evidence.
2. Add temporary logging or a debugger breakpoint inside the mocked method's real implementation (or use `doAnswer` to log when the stub is invoked) to see the actual wall-clock gap between the test's main-thread call returning and the async call landing.
3. Run the specific test in a tight loop (`for i in {1..50}; do mvn test -Dtest=ClassTest#method; done` or the IDE's "run N times") to reproduce the intermittency reliably rather than relying on CI to eventually show it.
4. If a `Thread.sleep` is already present, temporarily reduce the thread pool size to 1 or introduce artificial delay in the mock's answer to see if a longer/shorter sleep changes the failure rate -- confirms it's a race, not something else.

## Fix
Never synchronize on a sleep. Use Mockito's built-in timeout verification, which polls rather than blocking for a fixed duration, or make the async boundary awaitable in the test:

```java
// Polls up to 1000ms, succeeding as soon as the call is observed
verify(auditLogger, timeout(1000).times(1)).log(any());
```

Better when possible: make the async seam controllable in tests. Inject the `ExecutorService`/`Executor` as a dependency and substitute a synchronous "same-thread" executor (`Runnable::run`) in the unit test, so the call under test completes before `verify()` runs at all -- this removes the race entirely rather than tolerating it with a timeout:

```java
@Mock private AuditLogger auditLogger;
private final Executor sameThreadExecutor = Runnable::run;

// in the class under test, inject Executor rather than calling
// Executors.newFixedThreadPool(...) directly, so tests can substitute one
```

The underlying principle: prefer eliminating real concurrency at the unit-test boundary (fastest, fully deterministic) and reserve `timeout()`-based polling for cases where a same-thread substitute isn't feasible (e.g. testing the executor wiring itself, or a genuine multi-thread integration test).

## Pitfalls
Bumping `timeout()`'s duration higher and higher when a test still occasionally fails is a trap -- it masks a real bug (e.g. the async task sometimes never runs due to an unhandled exception) behind "just wait longer," and it slows down the whole suite as more tests adopt long timeouts defensively. If increasing the timeout doesn't reliably fix it, treat it as a real race or a swallowed-exception bug in production code, not a test tuning problem.

## Verify
Run the test in a loop of at least 50-100 iterations locally (or via CI's repeat-job feature) after applying the fix and confirm zero failures, not just "it passed a couple of times" -- intermittent failures by definition need a higher sample size to trust a fix.
