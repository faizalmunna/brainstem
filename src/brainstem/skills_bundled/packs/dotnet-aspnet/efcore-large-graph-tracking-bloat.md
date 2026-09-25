---
name: efcore-large-graph-tracking-bloat
description: Diagnose an EF Core app with growing memory use and slow SaveChanges because queries track large object graphs that are only ever read, never updated.
triggers: ["savechanges getting slower over time", "ef core memory grows per request", "changetracker huge", "dbcontext memory bloat", "read-only query tracking entities"]
permissions: ["READ"]
---

## Symptom
Memory usage climbs over the lifetime of a long-lived `DbContext`
(or within a single request that loads a lot of related data), and calls
to `SaveChanges()`/`SaveChangesAsync()` get progressively slower even
when the code only intends to read data and doesn't call `Update()`
explicitly. Often shows up as a request that loads a report, dashboard,
or export endpoint being disproportionately slow to "save" data it never
meant to modify, or as memory that never comes back down within a
request-scoped context that lives longer than expected (e.g. captured in
a loop or a long batch job).

## Likely causes
1. **Read-only queries executed without `AsNoTracking()`** -- by default
   EF Core's change tracker keeps a reference to every entity instance
   materialized by a query, plus a snapshot of its original values, so it
   can detect changes on `SaveChanges()`; for a large read-only result set
   this multiplies memory per entity and makes `SaveChanges()` do a full
   change-detection scan across everything ever loaded on that context
   instance, not just what actually changed.
2. **Eager-loading (`Include`) pulling in more of the object graph than
   the endpoint actually needs** -- e.g. loading a parent entity with
   `Include(x => x.Children).ThenInclude(c => c.GrandChildren)` when the
   endpoint only displays parent-level summary fields, tracking (and
   holding in memory) thousands of unnecessary child/grandchild entities.
3. **A `DbContext` with a longer-than-request lifetime** (registered with
   the wrong lifetime, reused across a loop, or held by a singleton/
   background job) accumulates tracked entities across many operations
   instead of the tracked set being cleared when the context is disposed
   at the end of a request -- the bloat is really a scope-lifetime bug
   wearing a performance-symptom disguise.
4. **Explicit `ChangeTracker.DetectChanges()` calls, or APIs that trigger
   it implicitly (like `Find`, `Add`, or accessing `ChangeTracker.Entries()`)
   invoked repeatedly in a loop** over a large tracked set, each call
   re-scanning every tracked entity for changes -- O(n) per call becomes
   O(n * loop iterations).

## Diagnose
- Check whether the query in the suspect code path calls
  `AsNoTracking()`/`AsNoTrackingWithIdentityResolution()` -- grep the
  repository/query layer for LINQ queries against the `DbContext` missing
  it on paths that only render/return data.
- Log `context.ChangeTracker.Entries().Count()` before and after the
  suspect operation (in a diagnostic/dev build, not production) to see
  how many entities are actually being tracked relative to what the
  endpoint needed to display.
- Use `context.ChangeTracker.DebugView.LongView` in a debugger or dev
  logging to inspect exactly which entity types and navigation properties
  are tracked after a request -- this usually reveals an unexpectedly
  deep `Include` chain.
- Profile `SaveChangesAsync()` duration against the tracked entity count
  across a few requests -- if duration scales with total tracked count
  rather than with the number of actually-changed rows, that confirms
  change-detection overhead from over-tracking, not an actual database
  round-trip cost.
- Confirm the `DbContext` lifetime in DI registration
  (`AddDbContext` defaults to scoped) and check for any code that
  manually keeps one instance alive across multiple logical operations
  (a static field, a singleton holding a `DbContext`, or a long-running
  loop that never creates a new scope).

## Fix
- Add `.AsNoTracking()` to every query whose results are only read,
  serialized to a DTO/view model, or returned as-is -- this is the
  default posture for GET-style read paths; reserve tracked queries for
  code that will actually call `Update`/modify entities and later
  `SaveChanges()`.
- Narrow `Include()` chains to exactly what the endpoint needs, or
  project directly into a DTO with `.Select()` instead of loading full
  entities -- projection avoids materializing (and tracking) navigation
  properties the caller never touches.
- For genuinely large read-heavy operations (batch exports, reports),
  consider `AsNoTrackingWithIdentityResolution()` if the same entity
  appears multiple times in the result set and you need reference
  equality without full change tracking, or process results in a
  streamed/paged manner rather than materializing everything at once.
- Ensure `DbContext` lifetime matches the unit of work -- scoped per
  request is the default and correct choice for web apps; for batch jobs,
  create a fresh scope (and fresh `DbContext`) per batch/iteration rather
  than reusing one context across the whole job.

## Pitfalls
- Slapping `AsNoTracking()` everywhere, including on entities the code
  later tries to `Update()` and save, causes a different bug: EF Core
  won't detect the changes because the entity was never tracked, so the
  "fix" silently breaks writes -- audit each query's actual downstream
  use (read vs. write) before changing its tracking behavior, don't
  apply it as a global find-and-replace.
- Switching to `AsNoTracking()` doesn't fix a captive/long-lived
  `DbContext` bug (cause 3) -- if the context itself is held too long,
  untracked results still accumulate elsewhere (e.g. in an
  application-level cache) and the underlying scoping mistake will cause
  other issues (stale data, concurrency exceptions) independent of
  tracking.

## Verify
Re-run the profiling step from Diagnose after applying `AsNoTracking()`/
narrowed includes: confirm `ChangeTracker.Entries().Count()` after the
read-only endpoint runs is at or near zero, and that `SaveChangesAsync()`
timing on unrelated write operations sharing the same context type is no
longer correlated with how much data the read endpoint previously loaded.
