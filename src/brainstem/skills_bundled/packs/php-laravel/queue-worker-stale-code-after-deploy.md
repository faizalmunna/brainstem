---
name: queue-worker-stale-code-after-deploy
description: A bug fix or new feature is deployed but queued jobs keep executing the old code path for minutes or hours afterward.
triggers: ["queue worker running old code", "deployed fix but queue still broken", "laravel queue:restart needed", "queued job using stale class after deploy"]
permissions: ["READ"]
---

## Symptom
Code is deployed (a bug fix, a changed job's logic, an updated class a
job depends on), the fix is confirmed correct by reading the deployed
files on disk, and yet jobs processed by the queue worker keep exhibiting
the *old* buggy behavior -- sometimes for a surprisingly long time after
the deploy, until eventually (often after an unrelated restart) it
resolves itself.

## Likely causes
1. **A long-running `queue:work` process has the old code loaded in PHP
   memory and keeps using it** -- unlike a web request (PHP-FPM tears down
   and reloads the application on most requests/workers depending on
   opcache config), a queue worker process is a long-lived PHP process
   that boots the framework once and then loops, pulling and processing
   jobs, without reloading classes from disk on every job -- a deploy
   that doesn't explicitly restart these processes leaves them running
   the pre-deploy code indefinitely.
2. **`php artisan queue:restart` is missing from the deploy script
   entirely**, or is present but the process manager (Supervisor,
   Horizon, systemd) isn't actually configured to restart workers in
   response to the restart signal -- `queue:restart` works by setting a
   cache-based timestamp that running workers check *between* jobs and
   exit gracefully after; if the process manager doesn't then spawn a
   fresh worker (`autorestart`/`numprocs` misconfigured), the old worker
   process may not even receive or act on the signal as expected.
3. **The restart signal relies on a cache store, and that cache store
   itself was just cleared or is misconfigured (e.g. a `file` cache
   driver not shared across the servers running workers)** -- if the
   worker can't read the restart timestamp because of a cache
   inconsistency, it never notices it should exit, and keeps running the
   stale code indefinitely instead of just until its next natural
   restart.
4. **Jobs were already queued (serialized) *before* the deploy** and
   reference a job class whose logic changed -- this isn't actually a
   worker-restart problem, but looks identical from the outside: jobs
   enqueued pre-deploy run with the code that existed at enqueue-serialization
   time for their class structure, and even a freshly restarted worker
   processing an already-queued job can behave unexpectedly if the job's
   constructor/property structure changed incompatibly between enqueue
   and processing time.

## Diagnose
- Check the deploy script/pipeline for a `php artisan queue:restart`
  step, and confirm it runs *after* the new code is fully in place (not
  before, and not racing with it).
- Check how workers are supervised: for Supervisor, inspect the relevant
  `.conf` file's `autorestart`/`stopsignal` settings; for Horizon, check
  `php artisan horizon:status` and whether the deploy script calls
  `php artisan horizon:terminate` (which Horizon-managed supervisors
  should then restart with fresh code) rather than relying on
  `queue:restart` alone.
- Confirm the cache driver used for the `queue:restart` signal
  (Laravel's default cache store) is actually shared/reachable
  consistently across every server running a queue worker -- a `file`
  cache driver on a per-server disk means the restart signal set on one
  server is invisible to workers on other servers.
- Check process uptime for the worker (`ps aux | grep queue:work`, or the
  process manager's own uptime reporting) and compare it against the
  deploy timestamp -- a worker process older than the most recent deploy
  is running pre-deploy code by definition.
- For the specific-job-structure case, check whether the failing jobs
  were enqueued before or after the deploy timestamp (job creation
  time, if tracked, or approximate via `failed_jobs`/monitoring
  timestamps) to distinguish "stale worker" from "stale already-queued
  job payload."

## Fix
- Add `php artisan queue:restart` as a standard step in every deploy
  script, placed after all new code and config are in place, so every
  currently-running worker exits gracefully after finishing its current
  job and gets respawned by the process manager with fresh code.
- Ensure the process manager is actually configured to respawn workers
  automatically after `queue:restart` causes them to exit (Supervisor's
  `autorestart=true`, or Horizon's own process management) -- the
  `queue:restart` command only asks workers to stop; something else has
  to bring them back for the deploy to actually take effect.
- Use a cache driver for the restart signal (and for anything else
  requiring cross-server coordination, like `withoutOverlapping`) that's
  genuinely shared across every server running workers -- `redis` or
  `database`, not `file`, in any multi-server deployment.
- For job-payload-structure changes, prefer additive/backward-compatible
  changes to job classes across a deploy boundary when the queue may
  still hold jobs enqueued under the old class shape, or drain the queue
  (let it empty out) before deploying a breaking structural change to a
  job class.

## Pitfalls
- Restarting workers on a fixed schedule (e.g. hourly cron) as a
  workaround instead of tying the restart to actual deploys either
  restarts too often (wasting the warm-up cost, interrupting in-flight
  jobs unnecessarily) or not promptly enough (stale code still runs for
  up to the schedule interval after a deploy) -- tie the restart directly
  to the deploy event.
- Killing worker processes forcefully (`kill -9`) instead of using
  `queue:restart`'s graceful signal can terminate a job mid-execution,
  leaving partial side effects and an ambiguous state in `failed_jobs`
  (or no record at all) -- graceful restart lets the current job finish
  before the process exits.
- Assuming Horizon handles this automatically without configuring
  `horizon:terminate` in the deploy script -- Horizon still needs to be
  told to cycle its managed processes on deploy; it doesn't detect code
  changes on its own.

## Verify
Make an observable, deploy-only change to a queued job's logic (e.g. a
log message with a version string), deploy it through the normal
pipeline, and immediately enqueue a fresh job -- confirm the *new* log
message appears, not the old one, and confirm via the process manager
that the worker process handling it has a start time after the deploy
completed rather than being a long-lived pre-deploy process.
