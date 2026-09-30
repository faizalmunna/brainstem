---
name: activerecord-callback-infinite-loop
description: Fix a stack overflow or hung request caused by two associated ActiveRecord models saving each other in an unintended callback loop.
triggers: ["SystemStackError rails", "callback infinite loop", "model save triggers infinite recursion", "after_save calling save on association loops forever", "rails stack level too deep"]
permissions: ["READ"]
---

## Symptom
Saving one record (directly, or via `update`) either hangs the request,
raises `SystemStackError: stack level too deep`, or -- in a milder form --
just runs noticeably slower than expected and the logs show the same two
models' callbacks (`before_save`, `after_save`, `after_commit`) firing
back and forth several times per request instead of once each.

## Likely causes
1. **Two associated models each have a callback that saves the other**
   (e.g. `Order#after_save` touches/saves `Customer`, and
   `Customer#after_save` touches/saves `Order`) with no guard against
   re-entrancy, so each save triggers the other's callback, which
   triggers the first again.
2. **A callback calls `save`/`update` on `self` inside its own
   `before_save`/`after_save`**, directly or through a chain of method
   calls, without checking `changed?`/`saved_change_to_attribute?` first
   -- every save re-triggers the same callback on the same record.
3. **`after_commit`/`after_save` callback recalculates and persists a
   derived value (a cached total, a counter) that itself is watched by a
   callback on the same or associated model**, so writing the derived
   value re-fires the observer that recalculates it.
4. **A callback added to a shared concern/module is included in both
   related models**, each independently deciding to sync the other on
   every save, without either side being aware the other model has the
   same behavior -- common after extracting a "keep two models in sync"
   concern without checking for symmetry.

## Diagnose
- Reproduce the save that hangs/errors and read the backtrace from
  `SystemStackError` -- it repeats the same few method names
  (`save`, callback method names) far more times than the model count,
  confirming a cycle rather than a single slow chain.
- Add a temporary `Rails.logger.debug` (or a debugger breakpoint) at the
  top of each suspected callback method printing the record's class,
  id, and `changed_attributes` -- run the save and read the log in order
  to see which model's callback triggers which other model's save.
- Search both models (and any shared concerns/modules they include) for
  `after_save`, `before_save`, `after_commit`, and `after_update` blocks
  that call `save`, `save!`, `update`, `update!`, or `touch` on an
  association.
- Check whether any of those callbacks guard on `saved_changes?` or
  compare old/new values before writing -- an unconditional write in a
  callback is the direct cause of unbounded re-triggering.

## Fix
- Break the cycle by making at most one side of the relationship
  responsible for keeping the pair in sync, and have it write directly
  (`update_column`/`update_columns`, which skips callbacks and
  validations) rather than through `save`/`update`, so the write doesn't
  re-trigger the other model's callback chain.
- If callbacks must remain symmetric, guard each one to only act when the
  relevant attribute actually changed (`if: -> { saved_change_to_total? }`)
  and to write only the derived attribute via a callback-skipping method,
  so a no-op recalculation doesn't cascade.
- Prefer `after_commit` over `after_save` for cross-model side effects
  that themselves trigger further writes -- it runs once per transaction
  after everything is durable, which makes it easier to reason about and
  to add idempotency guards around, rather than firing mid-transaction
  where nested saves compound.
- For counter/derived-value sync specifically, use Rails' built-in
  `counter_cache` or a dedicated recalculation job triggered once, rather
  than peer callbacks watching each other -- see the counter-cache skill
  in this pack for that specific pattern.

## Pitfalls
- Reaching for `update_column` to "just stop the loop" without also
  fixing the underlying design skips validations and other callbacks
  permanently for that write path, which can silently let invalid data
  through elsewhere in the app that relies on those callbacks running.
- Adding a boolean "syncing" flag/thread-local to short-circuit re-entrant
  callbacks works but is easy to leave set if an exception is raised
  mid-callback (skipped `ensure`), permanently disabling the sync for
  that process until restarted -- always wrap the guard-set/unset in
  `ensure`.
- Fixing the immediate two-model loop but leaving a third model in the
  same sync graph untouched, so the loop reappears through a different
  path once that third model's callback is exercised by a different code
  path.

## Verify
Write a model/integration test that updates one side of the relationship
and asserts the total number of `UPDATE`/`INSERT` statements issued (via
`assert_queries_count` or a SQL log count) is small and bounded --
not just that the test doesn't time out. Also manually trigger the
original save path in a console with `ActiveRecord::Base.logger = Logger.new(STDOUT)`
and confirm each model's callback fires exactly once.
