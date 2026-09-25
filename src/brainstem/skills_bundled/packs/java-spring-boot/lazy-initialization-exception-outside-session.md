---
name: lazy-initialization-exception-outside-session
description: Diagnose a Hibernate LazyInitializationException thrown when code accesses a lazily-fetched association after its originating session has already closed.
triggers: ["lazyinitializationexception", "could not initialize proxy no session", "failed to lazily initialize a collection", "hibernate session closed error", "lazy loading exception outside transaction"]
permissions: ["READ"]
---

## Symptom
Code accesses a lazily-fetched field or collection on a JPA entity
(`order.getLineItems().size()`, `customer.getAddress().getCity()`) and
gets `org.hibernate.LazyInitializationException: failed to lazily
initialize a collection/proxy ... no Session` (or "could not initialize
proxy - no Session"), even though the entity was loaded successfully
moments earlier without error. The exception happens specifically when
the access occurs *after* the code has left the scope that originally
loaded the entity -- a different method, a different thread, the view
layer, or after the request's transaction has already committed.

## Likely causes
1. **The Hibernate session (and its transaction) has already closed by
   the time the lazy field is accessed** -- the entity was loaded inside
   a `@Transactional` method, returned from it, and the lazy association
   is touched later (e.g. in a controller, a serializer, or a test
   assertion) outside any active session.
2. **The loading method's `@Transactional` boundary is narrower than
   assumed** -- e.g. `@Transactional(readOnly = true)` on a repository
   call but the lazy access happens in a *calling* method that isn't
   itself transactional, so the session closes the instant the
   repository call returns.
3. **A background thread or async task receives a detached entity**
   passed from a request thread (e.g. handed to `@Async`, an executor,
   or a message queue producer) and tries to touch its lazy fields --
   the original session is tied to the original thread/transaction and
   was never available to the new thread.
4. **Open-Session-In-View (OSIV) was relied on implicitly and then
   disabled** -- some teams' code never explicitly manages fetch
   boundaries because OSIV kept a session open through the whole
   request/view rendering; disabling `spring.jpa.open-in-view` (which
   Spring Boot now warns is on by default and recommends turning off)
   surfaces every place that was implicitly depending on it.

## Diagnose
- Get the full stack trace, not just the exception message -- it shows
  exactly which line accessed the lazy association and, walking up,
  whether that line is inside or outside the method carrying
  `@Transactional`.
- Check `spring.jpa.open-in-view` in the application properties -- if
  unset, Spring Boot defaults it to `true` and logs a startup warning;
  confirm whether that warning is present and whether OSIV is being
  relied upon versus already disabled (a recent change to `false` is a
  common trigger for a wave of these exceptions appearing at once).
- For the specific entity, check the association's fetch type
  (`@OneToMany`, `@ManyToOne`, etc.) -- confirm it's actually `LAZY`
  (the JPA/Hibernate default for collections) rather than assuming; some
  reports of this exception are really about a different association
  than the one suspected.
- Reproduce with a minimal test: load the entity inside a transactional
  method, return it, and access the lazy field from the test method
  body outside any transaction -- confirms the boundary issue in
  isolation from unrelated business logic.

## Fix
Choose the fetch strategy deliberately at the point of the query rather
than patching the symptom at the point of access:
- **Fetch what's needed inside the original transaction**, either via a
  `JOIN FETCH` in the JPQL/HQL query, an entity graph
  (`@EntityGraph(attributePaths = {"lineItems"})`), or by explicitly
  calling `Hibernate.initialize(order.getLineItems())` before the
  transaction/session ends -- this is the most predictable fix because
  the data need is made explicit at the query site.
- **Return DTOs from the transactional/service layer instead of raw
  entities** when data crosses into the view or API-serialization layer
  -- map the needed fields into a projection or record while the session
  is still open, so nothing downstream can accidentally touch an
  unfetched association.
- If a specific screen genuinely needs open-ended, session-scoped lazy
  loading (rare, and usually a sign the read pattern should be a query
  instead), re-enabling OSIV for that specific path is a narrower and
  more honest choice than leaving it on globally by default.

## Pitfalls
- Reflexively changing every lazy association to `EAGER` to make the
  exception disappear fixes nothing structurally -- it just moves the
  cost to *every* load of that entity (including places that never
  needed the association), and commonly reintroduces the N+1 query
  problem or loads unbounded collections eagerly.
- Re-enabling `spring.jpa.open-in-view` project-wide to silence a
  handful of exceptions trades a loud, specific failure for a much
  subtler one: connections held open for the full request/render cycle,
  which shows up later as connection pool exhaustion under load, not as
  an obvious stack trace pointing at the cause.

## Verify
With `spring.jpa.open-in-view=false` set explicitly (don't rely on the
implicit default), exercise the previously-failing code path end-to-end
(through the real controller/API, not just the service method in
isolation) and confirm the lazy field renders/serializes correctly with
no `LazyInitializationException`, then check the query log to confirm
the fetch happened as one deliberate query (or a bounded `JOIN FETCH`),
not as a fallback default fetch.
