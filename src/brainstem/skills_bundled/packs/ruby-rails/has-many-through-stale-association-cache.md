---
name: has-many-through-stale-association-cache
description: Fix a has_many through association that keeps returning stale, pre-update records within the same request or object lifetime.
triggers: ["has_many through stale data", "association returns old records after update", "activerecord cached association not updating", "stale join model results rails", "association still shows deleted record"]
permissions: ["READ"]
---

## Symptom
A `has_many :through` association (e.g. `Doctor has_many :patients, through: :appointments`)
keeps returning the same set of records it returned earlier in the same
request, console session, or long-lived object -- even after code in
between clearly created, updated, or destroyed one of the join records or
the target records -- until the object is reloaded from scratch.

## Likely causes
1. **ActiveRecord caches association results in memory on first access**,
   and nothing in the code path re-triggers a query after a write that
   should invalidate it -- the classic case is writing through a
   *different* object reference to the same underlying row (e.g. updating
   `Appointment.find(id)` in one place while holding a stale `doctor`
   object loaded earlier that still has the old `patients` cached).
2. **The write happens through raw SQL, `update_all`, `delete_all`, or a
   different model class entirely**, none of which go through the
   in-memory association proxy that would otherwise know to invalidate
   its cache -- ActiveRecord's association caching only knows about
   writes made through that same association/object graph.
3. **The through-association's join model (`Appointment`) is destroyed or
   created without touching the parent object at all**, so the parent
   (`doctor`) object, if already loaded and held onto (in a background
   job, a long controller action, a memoized `helper_method`, or a
   Sidekiq worker that loads the record once at the top), never sees the
   change even though a fresh `Doctor.find(id).patients` would.
4. **A `has_many :through` combined with a scope or `distinct` is memoized
   at the wrong layer** -- e.g. a serializer or presenter that memoizes
   `@patients ||= doctor.patients.to_a` early in a request and reuses that
   memoized array after a later mutation in the same request.

## Diagnose
- Reproduce the staleness in a console: load the parent object, print the
  association, perform the update/destroy through a *different* object
  reference (or raw SQL), then print the association again on the
  *original* object without reloading -- confirm it still shows old data,
  proving it's an in-memory cache issue rather than a real persistence
  bug.
- Grep for `update_all`, `delete_all`, `insert_all`, or raw SQL
  (`ActiveRecord::Base.connection.execute`) anywhere in the write path for
  the join model or target model -- these bypass callbacks and
  association cache invalidation entirely.
- Check whether the parent object is loaded once and reused across a long
  operation (a batch job, a loop processing multiple steps, a
  memoized instance variable in a controller/service object) rather than
  being re-fetched or reloaded between the write and the read.
- Check for `||=`-memoized association reads in serializers, view helpers,
  or presenter objects that could be caching the association result
  earlier in the same request than where the mutation happens.

## Fix
- Call `doctor.patients.reload` (or `doctor.association(:patients).reload`)
  immediately after any write that should affect the association but
  didn't go through that association object -- this forces a fresh query
  and replaces the cached in-memory result.
- Prefer performing the mutation *through* the association itself when
  possible (`doctor.appointments.create!(...)`, `doctor.patients.delete(patient)`)
  rather than through a freshly-fetched separate object reference, so
  Rails' own association-cache invalidation handles it automatically.
- For long-lived objects (background workers processing multiple items,
  long controller actions), re-fetch the parent record fresh right before
  reading an association that another part of the same run may have
  mutated, rather than trusting an object loaded much earlier.
- If a service/presenter memoizes an association result, invalidate that
  memoization explicitly whenever the underlying data is known to change
  within the same object's lifetime, rather than relying on it staying
  fresh implicitly.

## Pitfalls
- Calling `.reload` on every association read "to be safe" defeats the
  purpose of Rails' caching and reintroduces N+1-style query overhead --
  reload specifically at the points where cross-object mutation is known
  to happen, not universally.
- `reload` on the association only invalidates that one association, not
  other cached associations or attributes on the same object that may
  also be stale for the same underlying reason -- if multiple things are
  stale, consider `record.reload` on the whole object instead.
- Assuming a `has_many :through` will reflect a change made via
  `update_all` because "the SQL definitely ran" -- the SQL running
  correctly and the in-memory Ruby object reflecting it are two separate
  concerns; conflating them is the root of this whole class of bug.

## Verify
In a test or console, load the parent object once, mutate the underlying
join or target data through a different code path (matching how the real
bug occurs -- a separate object reference, `update_all`, or a background
job), then assert that the association reflects the change only after an
explicit reload -- and confirm the fixed code path calls that reload (or
avoids the stale reference) by checking the association value directly
after the fix, without an explicit reload in the test itself.
