---
name: graphql-n-plus-one
description: Diagnose and fix N+1 database query problems in GraphQL resolvers, where a list query triggers one extra query per item.
triggers: ["graphql n+1", "n plus one query", "graphql slow query", "resolver too many queries", "dataloader", "graphql query count high"]
permissions: ["READ"]
---

## Symptom
A GraphQL query that returns a list of N items with a nested field (e.g.
`posts { author { name } }`) triggers roughly N+1 database queries (one
for the list, then one per item for the nested field) instead of a
constant small number -- visible as query count/latency scaling linearly
with list size, often only noticed once the list gets large in
production.

## Likely causes
1. **A per-item field resolver that queries the database directly for
   each parent object**, with no batching -- this is the default,
   naive way to write a nested resolver, and it's correct but doesn't
   scale.
2. **Nested resolvers several levels deep**, compounding the problem
   (N posts x M comments per post x their authors) into a much larger
   query count than a single list's length suggests.
3. **A batching mechanism (DataLoader or equivalent) exists in the
   codebase but a specific resolver bypasses it**, querying directly
   instead of going through the batched loader -- often introduced when a
   new field/resolver is added without following the established
   pattern.

## Diagnose
- Enable query logging (or a GraphQL-aware APM tool) for a request that
  returns a list with a nested field, and count actual database queries
  issued -- confirm it scales with list length rather than staying
  constant.
- Check the resolver for the nested field: does it call the database/ORM
  directly with the parent's ID, or does it go through a batching
  loader keyed by ID?
- If a DataLoader-style pattern already exists elsewhere in the codebase,
  check why this specific resolver isn't using it -- often a newer field
  added without following the pattern.

## Fix
- Introduce a batching loader (DataLoader in JS, `strawberry.dataloader`/
  equivalent in Python, or the batching pattern native to the GraphQL
  framework in use) for each type of nested lookup: the loader collects
  all requested IDs across the current tick/request and issues a single
  `WHERE id IN (...)` query instead of one query per item, then resolves
  each individual request from the batched result.
- Key loaders by the actual lookup (e.g. `authorById`, `commentsByPostId`)
  and reuse the same loader instance across all resolvers within one
  request, so unrelated parts of the same query that need the same data
  also benefit from the batching/caching.
- For deeply nested cases, apply the same batching pattern at each level
  independently -- fixing only the outermost N+1 still leaves inner
  levels unbatched.

## Pitfalls
- A DataLoader instance must be scoped per-request (not a singleton
  shared across requests), or cached results from one user's request can
  leak into another's, and batching windows can mix unrelated requests
  incorrectly.
- Batching hides the query count problem from a naive test that only
  checks correctness, not performance -- add an explicit query-count
  assertion (many test frameworks / ORMs support this) to the test for
  any resolver returning a list with nested fields, so a future regression
  is caught automatically.
- Over-eagerly batching *everything*, including single, one-off lookups
  that aren't actually repeated within a request, adds indirection with
  no benefit -- apply it specifically to the parent-list-plus-nested-field
  shape that causes N+1, not universally.

## Verify
Re-run the same query-count measurement from the diagnose step against a
list of varying sizes (e.g. 5, 50, 500 items) and confirm the query count
stays constant (a small fixed number) rather than scaling with list
length.
