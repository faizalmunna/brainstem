---
name: aspnet-captive-dependency-scoped-in-singleton
description: Diagnose an ASP.NET Core app where a scoped service injected into a singleton gets captured, causing data from one request to leak into later requests.
triggers: ["singleton has stale data from first request", "dbcontext shared across requests", "scoped service acting like singleton", "captive dependency di", "data from wrong user showing up"]
permissions: ["READ"]
---

## Symptom
A service registered as scoped (e.g. `DbContext`, a per-request
"current user" accessor, a unit-of-work) behaves as if it were a
singleton: the data it holds from the very first request that
constructed it keeps showing up in later, unrelated requests, or a
`DbContext` throws `ObjectDisposedException`/concurrency errors once
multiple requests hit it at once. Often first noticed as "user A's data
appeared in user B's response" or "this only breaks after the app has
been running a while, never on the first request."

## Likely causes
1. **A scoped service is constructor-injected directly into a singleton**
   -- the DI container resolves the scoped dependency once, at the
   moment the singleton itself is first constructed (typically app
   startup or first use), and holds that single instance for the
   singleton's entire lifetime, because the singleton has no per-request
   scope of its own to re-resolve from.
2. **A scoped service is captured indirectly** through another
   service that looks safe -- e.g. a singleton depends on a transient
   service, but that transient service depends on a scoped one, and DI
   still resolves the whole graph within whatever scope was active when
   the singleton was built, capturing the scoped instance transitively.
3. **`IServiceScopeFactory` is used correctly to create a scope, but the
   scope is created once at singleton-construction time and reused**
   instead of creating a fresh scope per unit of work -- this looks like
   the "correct" pattern (using a scope factory) but still captures one
   scope's services for the singleton's lifetime.
4. **A background/hosted service resolves a scoped dependency directly
   from the root `IServiceProvider`** in its constructor or `ExecuteAsync`
   instead of creating a scope per iteration, which is the hosted-service
   variant of the same captive-dependency bug.

## Diagnose
- Enable DI validation: in `Program.cs`, build the host with
  `ValidateScopes = true` (`Host.CreateDefaultBuilder` does this by
  default in Development) and `ValidateOnBuild = true` on the service
  provider options -- this makes the container throw
  `InvalidOperationException: Cannot consume scoped service ... from
  singleton` at startup instead of silently capturing it, for the direct-
  injection case.
- For the indirect/transitive case (which scope validation may not catch
  if the transient sits between them at registration time but not at
  resolution time), grep the singleton's full dependency graph for any
  service registered `AddScoped` and trace whether it's reachable without
  an explicit `CreateScope()` call.
- Add a log line in the suspect service's constructor printing an
  instance ID (`Guid.NewGuid()`) and confirm across two different HTTP
  requests whether the same instance ID appears both times -- if a scoped
  service prints the same ID on two unrelated requests, it's captured.
- For hosted services, check whether `ExecuteAsync` resolves scoped
  dependencies once outside its loop versus creating
  `IServiceScopeFactory.CreateScope()` inside each loop iteration.

## Fix
- Don't inject scoped services into singletons directly. Instead, inject
  `IServiceScopeFactory` (or `IServiceProvider`) into the singleton, and
  call `CreateScope()` to get a fresh scope -- and fresh scoped
  instances -- each time the singleton needs to do a unit of work,
  disposing the scope afterward (`using var scope = ...`).
- If the singleton only needs the scoped service for the duration of a
  single call, resolve it from the new scope right before use and let it
  go out of scope when the `using` block ends, rather than storing it as
  a field.
- Reconsider the lifetimes: sometimes the "singleton" doesn't actually
  need to be a singleton -- if its only reason for being a singleton is
  caching one expensive resource, extract that resource into its own
  singleton-scoped piece and keep the rest of the service scoped or
  transient.

## Pitfalls
- Injecting `IServiceProvider` (service locator) into everything to "solve"
  captive dependencies is itself an anti-pattern if overused -- it hides
  the real dependency graph and makes lifetime bugs harder to spot in
  review; prefer `IServiceScopeFactory` scoped explicitly around the unit
  of work, not a general-purpose service locator sprinkled everywhere.
- Creating a new scope per call but forgetting to dispose it (no `using`)
  leaks scoped resources (e.g. `DbContext` connections) just as surely as
  the captive-dependency bug it was meant to fix -- always dispose the
  scope.

## Verify
With `ValidateOnBuild = true` set, run the app's startup in a test/CI
environment and confirm it fails fast with the "cannot consume scoped
service from singleton" exception on the broken registration before the
fix, then confirm clean startup after switching the singleton to use
`IServiceScopeFactory`. Separately, hit the affected endpoint from two
concurrent simulated users and confirm each request's captured instance
ID (from the constructor log) is now unique per request.
