---
name: jpa-n-plus-one-query-loop
description: Diagnose a Spring Data JPA endpoint that issues one extra database query per row when iterating a lazily-fetched association in a loop.
triggers: ["n+1 query problem", "too many sql queries hibernate", "slow endpoint lots of small queries", "hibernate query per row", "select n+1 spring data jpa"]
permissions: ["READ"]
---

## Symptom
An endpoint or batch job that returns/processes a list of entities gets
dramatically slower as the list grows, and the database query log shows
one initial `SELECT` for the list followed by one additional `SELECT`
*per row* to fetch a related entity or collection -- N+1 total queries
for N rows, instead of one or two queries total. It's usually first
noticed as "this endpoint got slow after real data volume grew" rather
than in development with a handful of test rows, because the pattern is
invisible until N is large enough to matter.

## Likely causes
1. **A lazily-fetched association is accessed inside a loop over the
   parent collection** -- e.g. iterating `List<Order>` and calling
   `order.getCustomer().getName()` or `order.getLineItems().size()`
   for each one, where the association is `FetchType.LAZY` (the default
   for `@OneToMany`/`@ManyToMany`, and often explicitly set for
   `@ManyToOne`/`@OneToOne` too) -- each access triggers its own query
   because Hibernate has no way to know in advance that *all* rows will
   need it.
2. **A DTO projection or serializer walks a full lazy object graph**
   rather than the specific fields it needs -- e.g. a Jackson serializer
   or a mapper (MapStruct/manual) touching a nested lazy relationship on
   every element of a paginated result, hidden a few layers away from
   the obvious loop.
3. **A `@Query` or repository method returns the parent entities without
   any fetch join**, and a *different* layer than expected (a template,
   a report generator, a batch export step) is what actually walks the
   association -- so grepping only the repository/service layer for the
   loop misses where the N+1 is actually triggered.
4. **Pagination combined with a `JOIN FETCH` on a collection** -- a fix
   attempt that adds `JOIN FETCH` on a `@OneToMany` while also using
   `Pageable` silently produces incorrect/duplicated results or an
   in-memory pagination warning, so a naive "just add JOIN FETCH"
   fix can trade N+1 queries for wrong or memory-heavy behavior instead.

## Diagnose
- Turn on SQL logging with parameter binding
  (`spring.jpa.show-sql=true`, `logging.level.org.hibernate.orm.jdbc.bind=TRACE`,
  or a tool like p6spy/datasource-proxy) and hit the slow endpoint with a
  known number of rows (e.g. exactly 10) -- count the queries; roughly
  `1 + 10` distinct per-row `SELECT`s targeting the same association
  confirms N+1 rather than some other slowness source.
- Identify exactly which association is being lazily fetched by reading
  the repeated query's `WHERE` clause (it filters by the foreign key of
  the specific association) and matching it back to the entity's mapping
  annotation.
- Check whether Hibernate statistics are enabled
  (`spring.jpa.properties.hibernate.generate_statistics=true`) and look
  at `entity fetch count` / `collection fetch count` in the logged
  statistics summary -- this gives a precise count independent of eyeballing
  SQL log noise.
- Confirm the access point: search the code path exercised by the slow
  endpoint (service, mapper, serializer, template) for any access to the
  identified association, not just the obvious loop in the controller.

## Fix
Fetch the needed data in a bounded number of queries decided at the
query site, matched to the actual access pattern, rather than letting
per-row lazy loading decide it implicitly:
- For a to-one or bounded to-many association always needed alongside
  the parent, add a `JOIN FETCH` to the JPQL query or use an
  `@EntityGraph` on the repository method -- both make one query do the
  work of N+1.
- For a `@OneToMany`/`@ManyToMany` combined with pagination (where
  `JOIN FETCH` would break `LIMIT`/`OFFSET` correctness), fetch the page
  of parent IDs first, then issue a second query with
  `WHERE parent.id IN (:ids)` and a fetch join to load the associations
  for exactly that page in one extra query -- two total queries
  regardless of page size, instead of N.
- For read-heavy list endpoints, consider a dedicated projection/DTO
  query (`SELECT new com.example.OrderSummary(o.id, c.name, ...) FROM
  Order o JOIN o.customer c`) that selects exactly the fields the view
  needs in one query, sidestepping entity-graph fetch strategy
  altogether.

## Pitfalls
- Setting the association to `FetchType.EAGER` globally on the entity
  "fixes" this one call site but makes *every* load of that entity
  always pay the join cost, including code paths that never needed the
  association -- often trading one slow endpoint for a slower baseline
  everywhere, and can reintroduce cartesian-product blowups when
  multiple `@OneToMany` associations are all made eager on the same
  entity.
- Fixing N+1 with `JOIN FETCH` on a `@OneToMany` while still paginating
  with `Pageable` produces Hibernate's "firstResult/maxResults specified
  with collection fetch; applying in memory" warning -- the database
  returns the full unpaginated result set and Hibernate paginates in
  application memory, which can be worse than the original N+1 under
  real data volume; use the two-query ID-then-fetch pattern instead
  whenever pagination and a collection fetch both apply.

## Verify
With SQL/statement logging enabled, re-run the same fixed-row-count
request used to reproduce the bug and confirm the query count is now
constant (1 or 2 queries) regardless of N, then re-run it at a
significantly larger N (e.g. 500 rows) and confirm response time scales
roughly linearly with row count rather than query count, since query
count is now flat.
