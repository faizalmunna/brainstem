---
name: event-listener-not-firing-registration-mismatch
description: Code that dispatches a Laravel event runs without error but the listener's side effect (email, notification, cache bust) never happens.
triggers: ["laravel event listener not firing", "event fired but listener not called", "queued listener not running", "laravel event class not registered"]
permissions: ["READ"]
---

## Symptom
`event(new OrderShipped($order))` (or `OrderShipped::dispatch($order)`)
executes without throwing, the request/job completes normally, but
whatever the listener was supposed to do -- send a notification, bust a
cache key, update a related record -- never happens, with nothing in the
logs to indicate a failure because nothing actually ran.

## Likely causes
1. **The event-to-listener mapping was never registered**, or was removed
   during a refactor -- on Laravel versions using
   `app/Providers/EventServiceProvider.php`'s `$listen` array, a missing
   or mistyped entry means the listener class simply never gets attached;
   on Laravel 11+ using event discovery, the listener method's parameter
   type-hint (which is how discovery finds the mapping) may not exactly
   match the event class, so auto-discovery silently skips it.
2. **The listener is queued (`implements ShouldQueue`) and the queue
   worker isn't processing that connection/queue name**, or the job
   landed in `failed_jobs` -- the event dispatch itself succeeds
   immediately (queuing is fire-and-forget from the dispatcher's
   perspective), so the calling code has no way to know the listener
   never actually executed.
3. **The listener class was renamed or moved (namespace change) and the
   registration (explicit `$listen` array or a queued job's serialized
   class reference from before the rename) still points at the old,
   now-nonexistent class name** -- this can also affect *already queued*
   jobs serialized before the rename, which fail to unserialize and
   silently error out on a worker that isn't being watched.
4. **The event class itself was changed in a way that breaks matching**
   -- e.g. the event used to be dispatched with `event(new
   App\Events\OrderShipped(...))` and a refactor moved it to a different
   namespace or renamed it, but the listener registration (or discovery)
   still references the old fully-qualified class name.
5. **Event discovery cache is stale** -- `php artisan event:cache` was run
   (common in production deploy scripts, mirroring `config:cache`), and a
   listener added or changed after that cache was built isn't reflected
   until `event:clear`/`event:cache` is rerun, exactly analogous to the
   config-cache staleness issue but for events.

## Diagnose
- Run `php artisan event:list` to see Laravel's actual current
  understanding of every event-to-listener mapping -- if the expected
  listener isn't listed next to the event, that confirms a registration
  gap rather than a runtime/queue issue.
- Check whether `bootstrap/cache/events.php` exists (stale event cache)
  and compare its timestamp against the last code change involving this
  listener.
- If the listener implements `ShouldQueue`, check `failed_jobs` and the
  relevant queue's worker logs (`php artisan queue:work --queue=<name>
  -vvv` locally, or the process manager's logs in production) to confirm
  whether the job was ever dequeued and run, versus never picked up at
  all (check which queue connection/name the listener uses via its
  `viaQueue()`/`$queue` property against what the worker is actually
  listening to).
- Temporarily add a `Log::info()` at the very first line of the listener's
  `handle()` method and re-trigger the event -- if the log line never
  appears, the problem is registration/discovery, not something inside
  the listener's logic.
- Grep for the event's fully-qualified class name across the codebase
  (dispatch site, listener's type-hint, and any explicit `$listen` array
  entries) to catch a namespace mismatch after a move/rename.

## Fix
- Re-establish the mapping explicitly: for apps still using
  `EventServiceProvider`, add/correct the `$listen` array entry
  (`Event::class => [Listener::class]`); for apps relying on event
  discovery, ensure the listener's `handle()` method type-hints the exact
  event class (discovery matches on that type-hint, so a wrong or missing
  type-hint means it isn't found regardless of file location).
- After any rename/move of an event or listener class, run `php artisan
  event:clear` (and rebuild `event:cache` if the deploy pipeline uses it)
  immediately, and check for any already-queued jobs referencing the old
  class name -- those need to be handled explicitly (let them fail into
  `failed_jobs` and requeue after the fix, or purge them) rather than left
  to fail silently on a worker.
- For queued listeners, verify the queue connection/name the listener
  targets matches what the running workers actually consume (check
  `config/queue.php`'s default connection and the `queue:work` command's
  `--queue` argument in the process manager config, e.g. Supervisor or
  Horizon) -- a mismatch here means the job sits in a queue nothing is
  draining, indistinguishable from "the listener didn't fire" without
  checking the queue table directly.
- Include `event:cache`/`event:clear` in the same deploy-script step that
  handles `config:cache`, so the two staleness failure modes are fixed
  together rather than one being remembered and the other forgotten.

## Pitfalls
- Making the listener synchronous (removing `ShouldQueue`) just to make
  the bug "go away" during debugging, and forgetting to restore queuing
  before shipping, turns a background side effect into a blocking part of
  the request/response cycle -- fine for confirming the listener itself
  works, but not an acceptable permanent fix if the side effect (e.g. an
  external API call) was queued for latency/reliability reasons.
- Assuming `event:list` reflects reality without also checking for a
  stale `bootstrap/cache/events.php` -- if the cache is stale, `event:list`
  itself may report the cached (wrong) mapping rather than what the
  current code would discover, so clear the cache before trusting the
  listing in a debugging session.
- Fixing the registration but not accounting for jobs already serialized
  under the old class name sitting in the queue or `failed_jobs` --
  those will keep failing (or silently vanish, depending on the queue
  driver's handling of unserializable jobs) even after the code fix,
  giving a false impression that the fix didn't work.

## Verify
Trigger the event through the actual application flow (not a contrived
tinker call) and confirm, in order: `php artisan event:list` shows the
expected mapping, the listener's `handle()` log line (or its real side
effect) appears, and -- if queued -- the corresponding job shows as
processed (not pending, not failed) in the queue monitoring tool
(Horizon, or a `SELECT * FROM jobs`/`failed_jobs` check) within the
expected timeframe.
