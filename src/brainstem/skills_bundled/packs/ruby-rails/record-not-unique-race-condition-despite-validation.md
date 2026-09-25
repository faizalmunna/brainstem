---
name: record-not-unique-race-condition-despite-validation
description: Fix intermittent ActiveRecord::RecordNotUnique errors from duplicate records that a uniqueness validation was supposed to prevent.
triggers: ["ActiveRecord::RecordNotUnique despite validates_uniqueness", "duplicate records under load rails", "race condition creating duplicate rows", "unique constraint violation intermittent", "validates_uniqueness_of not working under concurrency"]
permissions: ["READ"]
---

## Symptom
The model has `validates :email, uniqueness: true` (or similar), and it
works correctly in manual testing and most of production traffic -- but
occasionally, especially under concurrent load (double-submitted forms,
retried API requests, two background jobs processing related work at the
same time), two records with the same "unique" value get created, or an
unhandled `ActiveRecord::RecordNotUnique` exception surfaces from a
database-level constraint instead of the expected validation error.

## Likely causes
1. **`validates_uniqueness_of`/`uniqueness: true` only checks the
   database at the moment the validation runs (a `SELECT ... WHERE email = ?`),
   which is inherently racy** -- two requests can both run that `SELECT`,
   both find no existing row, both pass validation, and both then `INSERT`,
   with the database only catching the collision if a unique index also
   exists at the database level (and if one doesn't exist, both `INSERT`s
   succeed, creating a true duplicate with no exception at all).
2. **A unique database index does exist, so the second `INSERT` correctly
   raises `ActiveRecord::RecordNotUnique`, but the application code has no
   rescue for it** -- the validation is assumed to be sufficient, so the
   database-level exception is unhandled and surfaces as a 500 error
   instead of a clean "already exists" response.
3. **The uniqueness check and the eventual insert happen far apart in
   time** (e.g. validation in a form object, then a background job
   performs the actual `create!` later, or a multi-step wizard validates
   early and commits at the end), widening the race window well beyond a
   single request's duration.
4. **Retried requests (client-side retry on timeout, or a background job
   retry) resubmit the exact same creation attempt**, and because the
   original request's transaction hadn't committed yet (or its response
   was lost even though it succeeded), the retry races the original.

## Diagnose
- Check the schema for an actual unique index on the column
  (`\d table_name` on Postgres, or read `db/schema.rb` for
  `add_index ..., unique: true`) -- if there's no database-level
  constraint, *any* concurrency can produce true duplicates with zero
  exceptions raised, which is the more severe version of this bug.
- Grep application logs (or an error tracker) for
  `ActiveRecord::RecordNotUnique` or the raw database driver's unique
  violation error class, and check whether it's rescued anywhere in the
  call stack or reaches the top as an unhandled 500.
- Reproduce under real concurrency, not sequentially: fire two (or more)
  identical creation requests at the same time (a small script with
  parallel threads/processes, or a load-testing tool) against a
  test/staging environment and confirm duplicates or exceptions actually
  occur -- a single sequential test will never expose this race.
- Check how far apart in the code (and in time) the uniqueness validation
  and the actual `INSERT` happen -- a wider gap (separate steps, separate
  requests, separate jobs) means a wider race window.

## Fix
- Add a unique index at the database level for every attribute (or
  attribute combination) that must be unique -- the application-level
  `validates uniqueness: true` is a UX nicety (fast, friendly error
  message) that reduces *how often* the race is hit, but only a database
  constraint actually prevents the duplicate from ever being persisted.
- Rescue `ActiveRecord::RecordNotUnique` around the create path
  specifically, and translate it into the same user-facing error the
  validation would have produced (e.g. re-run validation to populate a
  friendly `errors` message, or catch-and-retry as an update if the
  intent was find-or-create) -- don't let the database exception surface
  as an unhandled 500.
- For true find-or-create semantics under concurrency, use
  `find_or_create_by` inside a rescue-and-retry loop
  (attempt `create!`, rescue `RecordNotUnique`, then `find_by!` and return
  the existing record) rather than a plain `find_or_create_by` alone,
  since even that method has the same check-then-act race internally
  unless paired with a unique index and this rescue pattern.
- For scoped uniqueness (unique within a parent, e.g. unique slug per
  account), use a composite unique index matching the validation's scope
  exactly, and consider a database-level advisory lock or
  `SELECT ... FOR UPDATE` on the parent row for workflows that need to
  serialize a multi-step check-and-create sequence.

## Pitfalls
- Adding the unique index but leaving the create path unable to handle
  the resulting `RecordNotUnique` just trades "silent duplicate" for
  "occasional unhandled 500" -- both halves of the fix (constraint +
  rescue) are needed together.
- Wrapping the whole creation in a broad `rescue => e` to "handle" the
  race can mask unrelated errors (a different bug entirely) under the
  same generic handling -- rescue `ActiveRecord::RecordNotUnique`
  specifically, not a bare `StandardError`.
- A composite unique index that doesn't exactly match the validation's
  `scope:` option (e.g. validation scoped to `account_id` but the index
  only covers the bare column) leaves the same race open for the scoped
  case even though it looks fixed for the global case.

## Verify
Write a test that fires two (or more) concurrent creation attempts with
the same unique value -- using real threads/processes against the test
database, or a tool that simulates the interleaving -- and assert exactly
one record exists afterward and that no unhandled exception propagated
out of either request; the "losing" request should receive a clean,
expected error/response rather than a 500.
