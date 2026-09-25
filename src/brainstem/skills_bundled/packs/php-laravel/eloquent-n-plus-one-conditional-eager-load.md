---
name: eloquent-n-plus-one-conditional-eager-load
description: An Eloquent list endpoint still issues one query per row even though the controller already calls with() to eager load the relationship.
triggers: ["eager loading not working laravel", "with() still causing n+1", "eloquent n+1 despite eager load", "laravel query count scales with rows"]
permissions: ["READ"]
---

## Symptom
A controller or job already calls `Model::with('relation')->get()`, and the
relationship still shows up as one extra query per row in `DB::listen()`
output, Telescope, or Debugbar -- exactly the N+1 pattern eager loading was
supposed to prevent. It's often intermittent: fine in one request, N+1 in
another that looks like it hits the "same" code path.

## Likely causes
1. **The relationship is re-accessed with different constraints than the
   one that was eager loaded.** `with('comments')` loads the full
   relation, but the view/resource then calls `$post->comments()->where(...)`
   or `$post->comments->where(...)` with different filtering logic than
   what was preloaded -- calling the relationship as a *method* (with
   parens) always re-queries, ignoring the eager-loaded collection
   entirely, regardless of what was passed to `with()`.
2. **A conditional branch changes which relations are needed after the
   query already ran.** e.g. `with('author')` is called unconditionally,
   but a later branch also touches `$post->author->profile`, which was
   never eager loaded because the code path that needed it wasn't known
   until after the `with()` call was written.
3. **The eager load is nested but the constraint closure filters
   differently per parent than expected**, e.g.
   `with(['comments' => fn($q) => $q->where('user_id', $post->author_id)])`
   -- this closure can't actually reference `$post` per-row (it runs once
   against the whole batched query), so it silently produces wrong results
   or gets reworked into a per-row closure/accessor that re-queries.
4. **A resource/transformer or Blade partial accesses a relation that
   exists on a *different* model than the one that was eager loaded** --
   e.g. eager loading `Post::with('author')` but the Blade partial is
   actually iterating `$post->comments` and, inside that loop, accessing
   `$comment->author`, which was never touched by the original `with()`.

## Diagnose
- Turn on query logging for the exact request:
  `DB::listen(fn($q) => Log::info($q->sql, $q->bindings));` or open the
  request in Laravel Telescope/Debugbar and look at the query panel --
  count queries for the relation in question and confirm it scales with
  row count.
- Grep the view/resource/transformer for the relation name used as a
  **method call** (`->comments()->...`) versus a **property access**
  (`->comments`) -- the method call always re-queries even when the
  property was eager loaded.
- Check `$post->relationLoaded('comments')` at the point of use (temporarily
  dump it) -- `false` means the code path reached a place where the
  relation is needed but was never included in the original `with()`.
- Search for nested `with()` closures that reference the parent model's
  properties directly (`$q->where('x', $post->id)`) -- this is a signature
  bug where the closure is written as if it runs per-row, but it doesn't.

## Fix
- Always access eager-loaded relations as properties (`$post->comments`),
  never as method calls with additional constraints, if you want to reuse
  the preloaded collection. If you need a *differently filtered* view of
  the same relation, either eager load it under an aliased relation
  method (a second relationship definition with its own default
  constraints) or filter the already-loaded collection in memory with
  `$post->comments->where(...)` (Collection methods, not query builder
  methods -- no trailing `()` on the relation name).
- For nested constraints, use `with(['comments.author'])` for a plain
  nested eager load, or `with(['comments' => fn($q) => $q->where(...)])`
  only for a filter that's the *same for every parent row* -- if the
  filter genuinely depends on each parent, that's a sign the relationship
  should be redesigned (a scope, or a separate query keyed by the parent
  IDs) rather than forced into a closure that can't see the row.
- Audit every relation accessed inside a loop/resource/Blade `@foreach`
  against the `with()` call at the top of the controller -- every relation
  name reachable from that loop needs to appear in the eager load list,
  including relations-of-relations (`comments.author`, not just
  `comments`).

## Pitfalls
- "Fixing" this by switching to `Model::with('*')`-style broad eager
  loading (or loading every relation "just in case") pulls unnecessary
  data on every request and reintroduces the performance problem from the
  other direction -- eager load exactly what the current request's
  code paths use, verified by the query count, not by guesswork.
- Adding `->load()` (lazy eager loading) inside the loop as a quick patch
  still avoids raw N+1 the first time it's called, but if it's called
  once per row instead of once before the loop, it's exactly the same N+1
  with an extra layer -- `load()` must be called once, before iterating,
  on the whole collection (`$posts->load('comments.author')`), not inside
  the loop.
- Relying only on manual code review to catch this class of bug doesn't
  scale -- add an automated query-count assertion (e.g.
  `$this->assertQueryCountLessThan(n, fn() => ...)` via a package, or a
  raw `DB::listen()` counter in the test) for any endpoint that returns a
  list with relations, so a future code change that reintroduces the
  method-call-instead-of-property mistake fails CI instead of shipping.

## Verify
Re-run the query-log/Telescope check from the diagnose step against lists
of increasing size (e.g. 3, 30, 300 rows) and confirm the total query
count for the endpoint stays constant rather than growing linearly with
row count -- and confirm `relationLoaded()` returns `true` at every place
in the code that reads the relation.
