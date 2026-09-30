---
name: active-record-n-plus-one-eager-load-scope-mismatch
description: Fix an index page that still issues one query per row even though the controller already calls includes on the association.
triggers: ["includes not preventing n+1", "bullet gem still flags n+1 with includes", "eager loading not working rails", "n+1 query despite includes", "activerecord query count scales with rows"]
permissions: ["READ"]
---

## Symptom
A controller action already calls `Post.includes(:author)` (or similar),
but the rendered index page still issues roughly one extra query per row
in the log, and a tool like Bullet or `rack-mini-profiler` still flags an
N+1 -- the fix that's "supposed to work" doesn't, which is more confusing
than a plain N+1 with no `includes` at all.

## Likely causes
1. **A scope on the association or a `where` clause referencing the
   included table forces Rails to switch from a separate preload query to
   a single `LEFT OUTER JOIN`** (or vice versa) -- if the code then calls
   a method that only works with the other strategy (e.g. iterating and
   calling `.author` expecting a preloaded in-memory association after
   Rails silently fell back to `references`+join), the association is
   still fetched but the *specific attribute* accessed isn't part of the
   selected columns, triggering a fresh query per row.
2. **The association method called in the view differs from the one
   `includes`'d in the controller** -- e.g. controller does
   `Post.includes(:author)` but the view calls `post.author.profile.name`,
   which touches `profile`, an association nested one level deeper than
   what was eager-loaded.
3. **A conditional/dynamic scope is applied to the association itself**
   (`has_many :comments, -> { where(hidden: false) }`) and somewhere the
   code calls the *unscoped* raw association or a differently-scoped
   method (`post.comments.published` vs `post.comments`), which Rails
   cannot satisfy from the preloaded set and re-queries per row.
4. **The `includes` call happens on a relation that gets reassigned or
   re-queried later in the same action** (e.g. `posts = Post.includes(:author)`
   followed by `posts = posts.merge(some_other_scope)` where the scope
   uses `unscoped` or discards the preload), silently dropping the
   eager-load before it reaches the view.

## Diagnose
- Turn on SQL logging (`config.active_record.logger = Logger.new(STDOUT)`
  in development, or read `log/development.log`) and run the exact action;
  count SELECTs -- confirm they scale with row count, not just that
  Bullet fired once.
- Add `.explain` or check `to_sql` on the relation right before it's
  passed to the view, and compare it against what the view actually
  calls -- specifically list every dotted association chain the view
  touches (`post.author.profile.name`, `post.comments.published.count`).
- Grep the view/partial for every method call chained off the eager-loaded
  object and confirm each hop is included -- `includes(:author)` does not
  cover `author.profile` unless written as `includes(author: :profile)`.
- If a scoped association is involved, check whether the view calls the
  association through its scope name (`post.comments.published`) instead
  of the plain association (`post.comments`) -- these are different
  relations to ActiveRecord's preloader even if the `includes` used the
  plain association name.

## Fix
- Match the `includes` nesting exactly to what the view walks: `includes(author: :profile)`
  for `post.author.profile`, not just `includes(:author)`.
- If the view needs a filtered subset of an association (e.g. only
  published comments), either preload the plain association and filter
  in Ruby (`post.comments.select(&:published?)`, avoiding a second query
  but paying a memory cost), or define the scope such that it's what gets
  eager-loaded consistently everywhere it's used -- pick one and apply it
  at every call site, not just the index action.
- When a `where` on the joined table is required, use `.includes(:author).where(authors: { active: true })`
  and add `.references(:author)` (or let Rails infer it) so it uses a
  single JOIN instead of two separate preload queries -- but then any
  attribute access on `author` must come from columns actually selected,
  so avoid `select` clauses that drop association columns.
- Audit the whole request path (controller action, any decorator/presenter,
  every partial rendered) for the association chain rather than only
  checking the top-level controller line -- N+1s frequently hide in a
  partial three renders deep.

## Pitfalls
- Blindly adding `includes` everywhere "just in case" adds preload
  queries for associations the view never actually uses, wasting memory
  and query time without fixing anything -- only include what's walked.
- Switching to `.joins` instead of `.includes` to force a single query
  fixes the query count but silently loses the association's in-memory
  caching (`post.author` re-queries anyway unless you also add `.includes`
  or manually assign the association), reintroducing the exact N+1 it was
  meant to fix.
- Fixing the N+1 in the controller but not in a background job, API
  serializer, or export/CSV path that reuses the same model but assembles
  its own query -- each independent query entry point needs its own
  `includes` audit.

## Verify
Re-run the action with SQL logging against a seeded dataset of at least
20-50 rows and confirm the query count for the association-touching
attributes stays constant (a small fixed number, typically 2-3: one for
the main records, one per eager-loaded association) regardless of row
count. Add a request or controller spec asserting query count directly
(`assert_queries_count` in Rails 7.1+, or the `n_plus_one_control` /
Bullet gem in CI) so a future regression fails the build instead of
silently shipping.
