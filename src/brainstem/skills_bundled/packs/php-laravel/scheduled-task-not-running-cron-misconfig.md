---
name: scheduled-task-not-running-cron-misconfig
description: A task defined in Laravel's scheduler with schedule:run configured never actually executes, or stops executing after running fine for a while.
triggers: ["laravel scheduled task not running", "schedule:run not executing", "cron job laravel not firing", "withoutOverlapping stuck lock"]
permissions: ["READ"]
---

## Symptom
A task is defined via `$schedule->command(...)` /
`Schedule::command(...)` (or the `routes/console.php` equivalent on
newer Laravel versions) and was confirmed working at some point, but it
silently stops running -- no error, no log entry, just an absence of the
expected effect (a report never generated, a cleanup job never ran) that
someone eventually notices days later.

## Likely causes
1. **The server's crontab doesn't actually have the single required
   entry** (`* * * * * php artisan schedule:run >> /dev/null 2>&1`) --
   either it was never added on this specific server (common after
   provisioning a new server or migrating hosting), or it was silently
   removed by a deploy/provisioning script that regenerates the crontab
   from a template missing this line.
2. **`withoutOverlapping()` left a stale lock file/cache key from a
   previous run that crashed or was killed ungracefully** (server reboot,
   OOM kill, deploy that terminated the process mid-run) -- the lock
   normally clears itself when the command finishes, but an abrupt kill
   can leave it in place, and every subsequent scheduled run silently
   skips because it thinks a previous instance is still running.
3. **The task is correctly scheduled, but its `when()` condition (or an
   environment gate like `->environments(['production'])`) evaluates to
   false in the environment it's actually running in** -- e.g. the
   `APP_ENV` on the server doesn't match what the schedule definition
   expects, so the task is deliberately skipped, which looks identical
   to "not running" from the outside but is actually working as coded.
4. **Multiple app servers each run their own cron entry pointing at
   `schedule:run`, without a single designated scheduler server or a
   distributed lock**, and the task is scheduled without
   `onOneServer()`, so it either runs multiple times simultaneously
   (causing resource contention or duplicate side effects) or one
   server's clock/timezone drift causes it to fire at unexpected times
   relative to the others, masking as inconsistent execution.
5. **The task throws an exception early enough that Laravel's own
   scheduled-task failure hooks never get a chance to report it**, and
   there's no `emailOutputOnFailure()`/`onFailure()` callback configured,
   so a persistently-failing task looks identical to a never-running one
   from a hands-off monitoring perspective.

## Diagnose
- On the actual server, run `crontab -l` (or check the equivalent
  scheduled-task mechanism if not using cron, e.g. a container
  orchestrator's CronJob) to confirm the `schedule:run` entry exists,
  points at the correct PHP binary and project path, and runs as the
  expected user.
- Run `php artisan schedule:list` to see Laravel's own view of every
  registered task, its next due time, and whether `withoutOverlapping`/
  `onOneServer` is applied -- compare the "next due" time against when it
  was actually last observed to run.
- Check for a stale lock: `withoutOverlapping()` uses the cache (default
  driver) or a lock file under `storage/framework/schedule-*` depending
  on version/config -- inspect the relevant cache key or lock file's
  timestamp and compare it against how long the task normally takes to
  run; a lock far older than one normal run duration is stale.
- Run `php artisan schedule:run` manually on the server (not just
  locally) and watch for output/errors directly, including checking
  `$schedule->command(...)->when(...)` conditions by dumping the
  relevant config/env values the condition depends on.
- If multiple servers are involved, check cron entries on *all* of them,
  not just the one an engineer happens to have SSH access configured
  for, and confirm system clocks/timezones are in sync (`timedatectl` or
  equivalent) across servers.

## Fix
- Ensure exactly one, correctly-formed `schedule:run` cron entry exists
  on every server that's supposed to run scheduled tasks, and make its
  presence part of provisioning/deploy automation (not a manual one-time
  setup step) so a server rebuild doesn't silently drop it.
- For `withoutOverlapping()`, set an explicit, reasonable expiry
  (`withoutOverlapping($minutes)`) matched to how long the task actually
  takes plus margin, so a lock from a crashed run self-clears instead of
  blocking every future run indefinitely; for a currently-stuck lock,
  clear the specific cache key/lock file manually as an immediate
  unblock while fixing the underlying expiry.
- When running the scheduler from more than one server, add
  `onOneServer()` to tasks that must not run concurrently across servers
  (this requires a centralized cache driver like `redis`/`database`, not
  `file`, since it needs a lock visible to all servers) instead of
  assuming only one server's cron will ever fire at the relevant minute.
- Add `->emailOutputOnFailure(...)` or a custom `->onFailure(fn() =>
  ...)` callback (wired to the same alerting channel used for queue
  failures) to any task whose silent failure would matter, so a
  persistently-erroring task surfaces instead of looking indistinguishable
  from a task that simply never runs.

## Pitfalls
- Fixing a stuck `withoutOverlapping()` lock by just deleting it once and
  moving on, without adding an explicit expiry, means the exact same
  stuck-lock incident recurs the next time a run is killed abruptly
  (deploy, OOM, server reboot) -- fix the expiry, not just the symptom.
- Adding `onOneServer()` without first confirming the app uses a
  cache driver that actually supports the required atomic locking across
  servers (some drivers don't) gives a false sense of safety -- verify
  the configured cache driver is one Laravel's scheduler lock mechanism
  can rely on for cross-server coordination.
- Changing `when()`/`environments()` conditions to "just make it run" in
  a debugging session, without restoring the original intent afterward,
  can cause a task meant only for production to start running in staging
  too, with real side effects (real emails sent, real external API calls
  made) against non-production data.

## Verify
Confirm `php artisan schedule:list` shows the task's next-run time
approaching correctly, then wait for (or manually trigger via
`schedule:run` at the right minute) that time and confirm the task's real
effect happened (check its actual output artifact, not just "no error").
Separately, deliberately kill a run of the task mid-execution in a
non-production environment and confirm the next scheduled run still
fires once the configured `withoutOverlapping` expiry elapses, rather
than staying stuck.
