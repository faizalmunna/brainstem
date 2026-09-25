---
name: efcore-lazy-loading-proxy-n-plus-one
description: An EF Core query that looks like a single database call actually issues one additional query per row because lazy-loading proxies silently fetch a related entity on first access inside a loop.
triggers: ["ef core n+1 queries", "lazy loading too many database calls", "efcore proxy extra queries", "slow endpoint many small queries"]
permissions: ["READ"]
---

## Symptom

An endpoint that returns a list of entities is slow, and database
profiling (SQL Server Profiler, `IDbCommandInterceptor` logging, or an
APM tool) shows one query to fetch the list followed by one additional
query per row for a related entity, instead of the expected single query
(or one join) -- despite the code appearing to just iterate over an
already-loaded collection.

## Likely causes

- **Lazy loading proxies are enabled** (`UseLazyLoadingProxies()`) and a
  navigation property is accessed inside a `foreach`/LINQ iteration over
  the main result set, triggering a separate query per item the moment
  that property is touched.
- **`Include()` was used for one related entity but a *different* nested
  navigation property is accessed** later in the same method, which
  wasn't eagerly loaded and falls back to lazy loading per row.
- **The entities were fetched via a raw/tracked query far from where
  they're iterated** (e.g. fetched in one layer, iterated and their
  navigation properties accessed in a different layer/service), making
  it non-obvious at the point of iteration that lazy loading will fire.
- **A serialization step (returning entities directly to a JSON
  serializer) touches every navigation property on every entity**,
  triggering lazy loads during serialization rather than during
  application code the developer was looking at.

## Diagnose

1. Enable EF Core's logging (`.LogTo(Console.WriteLine, LogLevel.
   Information)` or a proper logging provider) around the slow endpoint
   and count the actual number of SQL statements issued for one request
   -- a count proportional to row count confirms N+1 directly.
2. Identify exactly which navigation property triggers the extra queries
   by checking the logged SQL for the specific related table being
   queried repeatedly.
3. Check whether `UseLazyLoadingProxies()` is enabled in the `DbContext`
   configuration, and whether the entity's navigation properties are
   declared `virtual` (required for the lazy-loading proxy to intercept
   access).
4. Trace where the entities are iterated and where navigation properties
   are actually accessed -- including inside a serializer or a view/
   template layer, which is easy to overlook as "not application code."

## Fix

Eagerly load every navigation property the request path actually needs
via `Include()`/`ThenInclude()` at the query that fetches the main
entities, rather than relying on lazy loading to fill gaps -- this turns
N+1 queries into one query (or a small, fixed number of them) regardless
of row count. If lazy loading is kept enabled for other parts of the
codebase, treat any endpoint returning a list plus related data as
requiring an explicit `Include()` review, and use `AsSplitQuery()` for
multiple `Include()`s that would otherwise produce a large single joined
result if that's proven to be a better tradeoff for the specific shape of
data. For serialization specifically, project to a DTO
(`.Select(x => new Dto { ... })`) that only pulls the fields actually
needed, rather than serializing tracked entities directly, which avoids
both accidental lazy-load triggers and over-fetching.

## Pitfalls

Don't respond to this by disabling lazy loading globally without
auditing what currently depends on it -- code elsewhere may rely on lazy
loading for infrequently accessed navigation properties where N+1 was
never actually a measurable problem, and turning it off without
`Include()`s in those paths causes null-reference-style failures (an
empty/uninitialized collection) instead of a performance problem. Also
don't over-eagerly `Include()` navigation properties "just in case" on
every query -- that trades one performance problem (N+1) for another
(always fetching more data than a given code path needs).

## Verify

Re-run the same request with EF Core query logging enabled and confirm
the query count is now fixed regardless of the number of rows returned
(test with both a small and a noticeably larger dataset to confirm the
count doesn't scale with row count). Measure end-to-end endpoint latency
before and after on a realistic dataset size to confirm the fix produced
an actual measurable improvement, not just fewer log lines.
