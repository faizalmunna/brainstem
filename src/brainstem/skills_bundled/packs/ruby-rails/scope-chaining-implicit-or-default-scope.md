---
name: scope-chaining-implicit-or-default-scope
description: Fix an ActiveRecord query that returns unexpectedly broad or narrow results after chaining two scopes together.
triggers: ["chained scopes returning wrong results", "activerecord or scope not working as expected", "merge scope drops conditions", "default_scope combined with or returns too many records", "scope chain produces wrong sql"]
permissions: ["READ"]
---

## Symptom
Chaining two scopes that individually return the expected records
produces a combined result that's either far larger than expected (looks
like the conditions were OR'd instead of AND'd) or, in the `.or` case,
raises `ArgumentError: Relation passed to #or must be structurally
compatible` -- or silently drops one side's conditions instead of raising,
depending on how the scopes were written.

## Likely causes
1. **`.or` is used to combine two relations that have different
   `where` values but the developer expected it to combine on top of a
   shared base scope** -- `Post.where(published: true).or(Post.where(featured: true))`
   correctly ORs those two conditions, but if the intent was "published
   AND (featured OR urgent)", the base condition needs to be inside both
   sides of the `.or`, not applied once outside it.
2. **A `default_scope` on the model is silently included in one branch of
   an `.or` chain but not thought about when reasoning through the
   combined SQL** -- `default_scope` conditions apply to every query
   including both sides of an `.or`, which can make the combined query
   behave differently than expected if the two scopes were designed
   assuming `unscoped` context.
3. **`merge` between two scopes with `where` clauses on the *same
   column* overwrites rather than ANDs**, when the second scope's
   condition is meant to narrow further but instead replaces the first
   (this happens specifically with certain non-`where` scope elements like
   `order`/`select`/`limit`, which `merge` replaces rather than combines,
   unlike `where`, which does combine with AND by default).
4. **A scope defined with `-> { where(...).or(where(...)) }` gets chained
   with another `where` afterward**, and operator precedence in the
   resulting SQL doesn't parenthesize the way the developer assumes --
   ActiveRecord does correctly parenthesize `.or` combinations, but a
   *raw SQL string* scope combining `AND`/`OR` without parentheses
   (`where("a = 1 OR b = 2 AND c = 3")`) follows SQL's own operator
   precedence (`AND` binds tighter than `OR`), which frequently
   surprises people who expect left-to-right evaluation.

## Diagnose
- Call `.to_sql` on the final chained relation and read the actual
  generated SQL -- for an `.or` chain, confirm both sides' complete
  `WHERE` clauses are what's expected and that parentheses group them the
  way the business logic intends.
- For a raw SQL string condition mixing `AND`/`OR`, explicitly check
  operator precedence by wrapping sub-conditions in parentheses in the
  generated SQL, or better, rewrite it as parenthesized ActiveRecord
  scope objects instead of a hand-written string.
- Check whether the model has a `default_scope` (`grep default_scope` in
  the model file) and mentally (or by calling `Model.unscoped.or(...)`
  experimentally) trace whether it's implicitly present in the query
  being debugged.
- For `merge`, compare `scope_a.merge(scope_b).to_sql` against
  `scope_a.to_sql` and `scope_b.to_sql` individually -- look specifically
  for which clauses (order, select, limit, where on the same column)
  appear from only one side instead of combined.

## Fix
- Build compound conditions explicitly with ActiveRecord's relation
  algebra rather than raw SQL strings: express "published AND (featured
  OR urgent)" as
  `Post.where(published: true).merge(Post.where(featured: true).or(Post.where(urgent: true)))`
  so the AND/OR grouping matches the SQL parentheses ActiveRecord
  generates, instead of relying on string concatenation and hoping
  precedence works out.
- When `default_scope` participates in a query being combined with `.or`,
  make the intended base condition explicit in both branches (or call
  `.unscoped` deliberately and re-add exactly the conditions wanted) so
  the combined query doesn't depend on implicit scope behavior that's
  easy to reason about wrong.
- For `merge` conflicts on the same attribute, decide explicitly which
  scope should win, or restructure so the two scopes constrain different
  attributes -- don't rely on `merge`'s replace-vs-combine behavior
  differing by clause type without having verified it via `.to_sql` for
  this exact pair of scopes.
- Prefer defining named scopes that already encode the correct grouping
  (`scope :featured_or_urgent, -> { where(featured: true).or(where(urgent: true)) }`)
  over composing raw `.or` calls ad hoc at call sites, so the logic is
  tested once and reused correctly everywhere.

## Pitfalls
- Avoiding `default_scope` entirely is sometimes recommended as a blanket
  rule, but the actual issue here is *implicit* interaction with `.or`/
  `merge`, not `default_scope` itself -- the fix is making scope
  composition explicit and verified via `.to_sql`, not necessarily
  removing `default_scope` if it's otherwise used correctly.
- `.or` in Rails requires both relations to be "structurally compatible"
  (same `includes`/`joins`/`references`) -- silencing the resulting
  `ArgumentError` by stripping one side's `includes` to make it "work"
  can reintroduce an N+1 that the `includes` was there to prevent.
- Testing only the two scopes in isolation (each returns correct results
  alone) and assuming the combination is therefore correct -- always add
  a test for the *combined* query's result set, not just each scope
  individually.

## Verify
Write a model spec that seeds records covering every combination of the
conditions involved (published-only, featured-only, both, neither, plus
whatever default_scope excludes) and assert the chained scope returns
exactly the expected subset -- checking IDs/count explicitly, not just
"returns something." Additionally assert on `.to_sql` containing the
expected parenthesization if the query is subtle enough that a future
refactor could silently change grouping without failing count-based
assertions on the current fixture data.
