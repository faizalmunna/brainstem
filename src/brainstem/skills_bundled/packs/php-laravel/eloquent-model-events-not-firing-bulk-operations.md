---
name: eloquent-model-events-not-firing-bulk-operations
description: Model observers and saving/deleting event hooks never run when records are changed through a query builder update() or delete() call.
triggers: ["eloquent observer not firing on update", "model events not triggered bulk update", "saving event not called laravel", "query builder update skips observers"]
permissions: ["READ"]
---

## Symptom
Logic in a model observer, or a `saving`/`saved`/`updating`/`deleting`
event hook (cache invalidation, an audit log entry, a computed column
update, a notification), is supposed to run whenever certain records
change -- and it works fine when tested by updating a single model
instance, but silently doesn't run when the same logical change happens
through a bulk operation like `Model::where(...)->update([...])` or
`Model::where(...)->delete()`.

## Likely causes
1. **`Model::where(...)->update([...])` operates directly on the query
   builder and issues a single SQL `UPDATE` statement**, bypassing
   Eloquent model hydration entirely for the affected rows -- no
   individual model instances are ever created, so there's nothing for
   `saving`/`updating`/`saved`/`updated` events (or observers listening
   to them) to attach to; this is documented Eloquent behavior, not a
   bug, but it's routinely missed because the method name (`update`)
   looks identical to the instance method that does fire events.
2. **Same root cause for deletes**: `Model::where(...)->delete()` issues a
   bulk `DELETE`/`UPDATE` (for soft deletes) without loading each matching
   record as a model instance, so `deleting`/`deleted` observers never
   run -- this is especially easy to hit accidentally when a scope is
   chained (`Model::inactive()->delete()`) since the bulk nature isn't
   obvious from the call site.
3. **A relationship's bulk update method was used instead of iterating**,
   e.g. `$user->posts()->update(['status' => 'archived'])` -- this reads
   like it's "through" the model but is still a query-builder bulk
   operation under the hood and has the same non-firing behavior as a
   plain `Model::where(...)->update()`.
4. **Code was refactored from a loop-based update (which did fire events)
   to a bulk update for performance**, without anyone realizing that the
   side effect the observer provided (e.g. recalculating a denormalized
   total, sending a notification) silently stopped happening -- this is
   often the actual root cause when the bug is a regression rather than
   something that "never worked."

## Diagnose
- Search the codebase for every place the affected model (or its
  relationships) is updated/deleted, and classify each call site: an
  instance method call (`$model->update(...)`, `$model->save()`,
  `$model->delete()`) fires events; a call starting from
  `Model::where(...)` or a relationship query builder
  (`$model->relation()->update(...)`) does not.
- Reproduce directly: add a temporary log line inside the observer/event
  hook, trigger the suspected bulk operation, and confirm the log line
  does not appear -- compare against triggering an equivalent
  single-instance update, which should log.
- Check whether the side effect that's missing (a cache key, a
  denormalized column, an audit row) actually depends on the event firing
  at all, or whether it's coincidentally also updated elsewhere -- this
  distinguishes "the event genuinely never ran" from "it ran but had no
  visible effect for another reason."
- Check git blame/history on the call site for a recent change from a
  loop (`foreach ($models as $m) { $m->update(...); }`) to a single bulk
  `update()` call -- this is a strong signal the bug is a performance
  refactor regression, not a pre-existing gap.

## Fix
- If per-record side effects (observers, event hooks) genuinely need to
  run for every affected row, iterate and save individually
  (`Model::where(...)->get()->each->update([...])` or a chunked loop for
  large sets) so each save goes through the full Eloquent lifecycle --
  accept the performance cost as the price of the side effect actually
  running, and use `chunkById()` for large tables to avoid loading
  everything into memory at once.
- If the side effect doesn't need to run per-record and was only
  happening incidentally via the model lifecycle (e.g. a cache-bust that
  could just as well happen once after the bulk operation), keep the bulk
  `update()`/`delete()` for performance and add the side effect explicitly
  right after the bulk call instead of relying on per-row events -- this
  is often the better fix when the bulk operation exists specifically
  because per-row iteration was too slow.
- For soft-deletes specifically, be aware that even
  `Model::where(...)->delete()` on a soft-deleting model still skips
  `deleting`/`deleted` events despite "delete" sounding like it should go
  through the same path as `$model->delete()` -- treat it the same as any
  other bulk operation for this purpose.
- Document the decision at the call site (a short comment) explaining
  *why* a bulk operation was chosen despite skipping model events, so a
  future maintainer doesn't "fix" it back into a slow per-row loop without
  understanding the tradeoff, or conversely doesn't assume events fired
  when they didn't.

## Pitfalls
- Converting every bulk operation back to a per-row loop "to be safe"
  defeats the reason bulk operations exist and can turn a fast
  maintenance job into one that times out or locks the table for an
  unacceptably long time on a large dataset -- only convert the specific
  operations whose side effects are actually required per-row.
- Relying on database triggers as a workaround to catch what Eloquent
  events miss adds a second, less visible place where business logic
  lives (outside the application codebase entirely), which is harder for
  the team to discover, test, and reason about than fixing the call site.
- Assuming `saved`/`updated` (the "after" events) are the only ones
  affected and leaving `saving`/`updating` (the "before" events, often
  used for validation or normalization) unexamined -- both classes of
  event are equally skipped by bulk operations, and a bulk update can
  therefore also skip data-normalization logic that the rest of the app
  assumes always ran.

## Verify
Trigger the actual bulk operation in question and confirm, in the
database, whether the dependent side effect (a cache key's new value, an
audit log row, a denormalized column) has the correct post-update state
-- not just that the primary rows were updated. If the fix was to add an
explicit post-bulk-operation step, verify it runs even when the bulk
operation affects zero rows (an empty `WHERE` match) or exits early, so
the fix doesn't silently rely on there being at least one row updated.
