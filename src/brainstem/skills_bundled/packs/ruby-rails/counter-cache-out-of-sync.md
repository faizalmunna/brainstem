---
name: counter-cache-out-of-sync
description: Fix a counter_cache column that drifts away from the actual count of associated records over time.
triggers: ["counter cache wrong count", "counter_cache out of sync", "association count column drifting", "comments_count wrong number", "reset_counters needed"]
permissions: ["READ"]
---

## Symptom
A `counter_cache` column (e.g. `posts.comments_count`) that's supposed to
mirror `post.comments.count` gradually drifts from the real number --
some posts show a count higher than their actual comment rows, others
show fewer, and simply calling `post.comments.count` (an actual `COUNT(*)`
query) gives a different, correct answer than reading the cached column.

## Likely causes
1. **Records were deleted with `delete`/`delete_all` instead of
   `destroy`/`destroy_all`** -- `delete` (and `delete_all`) removes rows
   directly via SQL without instantiating the model or running callbacks,
   and `counter_cache` decrementing is implemented as an
   `after_destroy`/`after_create` callback, so any deletion path that
   skips callbacks also skips the decrement.
2. **Records were created or updated via `update_all`, `insert_all`, raw
   SQL, or a data migration/rake task** that bypasses ActiveRecord
   callbacks entirely -- any bulk operation on the associated table that
   doesn't go through `save`/`create`/`destroy` on individual model
   instances leaves the counter cache exactly as stale as the callback it
   skipped.
3. **The association's `belongs_to` was added (or the `counter_cache: true`
   option added) *after* existing data was already present**, so the
   counts were never initialized correctly for pre-existing records --
   they start at zero (or a migration-supplied default) regardless of how
   many associated records already exist.
4. **A soft-delete pattern (a `deleted_at` column with a default scope
   excluding deleted rows) is used instead of actually destroying rows**,
   so `destroy`-based counter cache decrements never fire for a
   "soft delete" that just updates a column -- and if `comments.count`
   used for comparison also respects the default scope while the
   original increment didn't account for soft-delete semantics, the two
   numbers diverge over time as soft-deletes accumulate.
5. **Concurrent destroys race on the same parent's counter update** --
   the decrement itself (`UPDATE posts SET comments_count = comments_count - 1`)
   is safe as a single atomic SQL statement in modern Rails, but a custom
   counter-maintenance callback that reads-then-writes
   (`post.update(comments_count: post.comments.count - 1)`) instead of
   using the atomic decrement is vulnerable to lost updates under
   concurrent destroys.

## Diagnose
- Pick a handful of records where the count looks suspect and compare the
  cached column directly against a live count:
  `Post.find(id).comments_count` vs. `Post.find(id).comments.count`
  (the latter always issues a real `COUNT(*)`, ignoring the cache) --
  a mismatch confirms drift.
- Grep the codebase for `delete`, `delete_all`, `update_all`, `insert_all`,
  and raw SQL touching the associated model's table -- each is a
  candidate for a counter-cache bypass; check whether counter maintenance
  was hand-added alongside each one.
- Check whether `counter_cache: true` was added to the `belongs_to`
  after the tables already had data, by checking migration history dates
  against when the counter column was introduced versus how old the
  oldest affected records are.
- If soft-deletes are in play, check whether the counter increments on
  create but decrements only on hard `destroy` -- confirm what "delete"
  means in this codebase (an actual row removal, or a `deleted_at` flag)
  and whether the counter's semantics match.

## Fix
- Run `Post.reset_counters(id, :comments)` (or in bulk, iterate all
  affected ids) to recompute the cached column directly from a real
  count -- this is Rails' built-in repair mechanism and should be the
  immediate fix for already-drifted data.
- Replace any `delete`/`delete_all` calls on the associated model that
  are meant to reflect in the counter with `destroy`/`destroy_all` (paying
  the cost of loading and running callbacks), or, if the bulk-delete
  performance is required, explicitly decrement the counter in the same
  operation (`Post.decrement_counter(:comments_count, post_id)` for
  each affected parent, or a single grouped `UPDATE` if deleting many at
  once) rather than silently skipping it.
- For any bulk/raw-SQL write path that must remain callback-free for
  performance reasons, add an explicit, deliberate counter recalculation
  step immediately after it (either `reset_counters` for the affected
  parents, or a direct atomic decrement/increment matching the row count
  actually affected).
- For soft-delete schemes, don't rely on the built-in `counter_cache`
  callback at all (it doesn't know about soft-delete semantics) --
  maintain the counter explicitly in the soft-delete method itself
  (whatever sets `deleted_at`), decrementing atomically at that point, and
  keep the default-scoped `.count` and the cached column consistent by
  definition rather than by coincidence.
- Add a periodic reconciliation job (nightly or weekly) that spot-checks
  or fully recomputes counter caches for a sample or all affected
  associations and alerts on any drift found, as a safety net for
  whichever bypass wasn't anticipated.

## Pitfalls
- Running `reset_counters` fixes the data at that moment but doesn't fix
  the underlying bypass -- without also fixing the write path that
  skipped the callback, the count will drift again the next time that
  path runs.
- Switching every `delete_all` to `destroy_all` for correctness can be a
  serious performance regression on large bulk operations (loading every
  record and running full callback chains instead of one SQL statement)
  -- for genuinely bulk operations, an explicit atomic counter adjustment
  is usually the better trade-off than switching to per-record destroys.
- Assuming `counter_cache: true` retroactively backfills existing data --
  it only affects future creates/destroys from the moment it's added;
  existing rows still need an explicit `reset_counters` run once.

## Verify
After applying the fix, run `reset_counters` (or the reconciliation job)
across all affected records, then compare cached counts against live
`COUNT(*)` queries for a representative sample (or all records, if the
table is small enough) and confirm zero mismatches. Separately, exercise
the specific write path that caused the original drift (the bulk
delete/update path) end-to-end in a test and assert the counter column
reflects the correct count afterward without needing a manual
`reset_counters` call.
