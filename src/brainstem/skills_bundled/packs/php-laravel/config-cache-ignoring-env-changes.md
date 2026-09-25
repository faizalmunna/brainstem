---
name: config-cache-ignoring-env-changes
description: Updating a .env variable in production has no effect on the running application because php artisan config:cache already baked the old value in.
triggers: ["env variable change not taking effect laravel", "config cache ignoring .env", "artisan config:cache production bug", "changed env but app still using old value"]
permissions: ["READ"]
---

## Symptom
An environment variable is changed in `.env` (a new API key, a toggled
feature flag, a changed database host) and the deployed application keeps
behaving as if the old value were still set -- restarting PHP-FPM or the
web server doesn't help, and the change only "sticks" after someone
happens to run `php artisan config:clear` or redeploys from scratch.

## Likely causes
1. **`php artisan config:cache` was run at some point (often as part of a
   deploy script) and never re-run after the `.env` change.** Once
   cached, Laravel's config system stops reading `.env` entirely for any
   `env()` call inside `config/*.php` files -- it only reads the compiled
   `bootstrap/cache/config.php` file, so `.env` edits after caching are
   invisible until the cache is rebuilt.
2. **`env()` is called directly outside of `config/*.php`** (in a
   controller, a service class, `routes/web.php`), which works fine
   without caching but returns `null` after `config:cache` is run --
   Laravel explicitly does not support `env()` calls outside config files
   once cached, and this is a common source of confusion because the
   symptom looks identical to a normal cache-staleness issue but has a
   different fix.
3. **The deploy pipeline runs `config:cache` before the new `.env` file is
   in place**, e.g. secrets are synced from a vault/secrets manager after
   the artisan commands run, or the `.env` file is written by a step that
   races with the cache step -- so the cache is built from stale or
   default values even though the "current" `.env` on disk looks correct
   by the time someone checks it.
4. **Multiple app servers behind a load balancer have inconsistent
   caches** -- the config cache was rebuilt on one server (e.g. the one an
   engineer SSH'd into to debug) but not the others, so the symptom
   appears intermittent depending on which server handles the request.

## Diagnose
- Check whether `bootstrap/cache/config.php` exists on the affected
  server(s) -- its presence means config is cached and `.env` is not being
  read live.
- Run `php artisan config:show <key>` (Laravel 9+) or dump
  `config('the.key')` via `php artisan tinker` to see what value the app
  is actually using right now, and compare it against the current `.env`
  value on that same server.
- Grep the codebase for `env(` calls outside the `config/` directory --
  each one is a landmine that behaves differently once caching is
  introduced.
- Review the deploy script/CI pipeline for the order of operations:
  confirm `.env` (or secrets injection) happens strictly before
  `config:cache`, and that `config:cache` runs on every app server, not
  just the one someone deployed from interactively.

## Fix
- Move any `env()` call found outside `config/*.php` into a config file
  (add a new key under `config/services.php` or an app-specific config
  file) and reference it everywhere else via `config('services.thing.key')`
  instead of `env('THING_KEY')` -- this is the supported pattern and
  survives `config:cache` correctly.
- Ensure the deploy pipeline always runs `config:clear` (or simply
  reruns `config:cache`) as the last step after any `.env`/secrets update,
  on every server that serves traffic, not just one -- treat config
  caching as something that must be redone atomically with every deploy
  and every secrets rotation, not a one-time setup step.
- For secrets that rotate independently of code deploys (API keys,
  rotated credentials), add an explicit runbook step or automation that
  reruns `config:cache` (or restarts workers/app servers that reload it)
  whenever the secret changes, since that's a different trigger than a
  normal code deploy.
- In multi-server deployments, make config caching part of the deploy
  script that runs identically on every node (e.g. via the deployment
  tool's "run on all servers" step, not a manual SSH command), so no
  server can drift to a different cached state than the others.

## Pitfalls
- Reflexively adding `config:cache` to "fix" a slow boot without also
  auditing for stray `env()` calls outside config files introduces this
  exact bug into a codebase that didn't have it before -- treat enabling
  config caching as a change that requires the `env()`-outside-config
  audit as a prerequisite, not an afterthought.
- Running `config:clear` in production as a permanent workaround (instead
  of fixing the pipeline to recache after every change) gives up the
  performance benefit config caching exists for, and can reintroduce
  filesystem-permission or `.env`-parsing overhead on every request under
  load.
- Assuming "config cache" and "route cache" behave the same way and
  fixing one but not the other -- `php artisan route:cache` has its own
  independent staleness failure mode (e.g. closures in routes), so a
  deploy script needs to manage both, not just whichever one someone
  happened to notice was stale.

## Verify
On the affected server, change a test config value in `.env`, run `php
artisan config:cache`, and confirm `php artisan config:show <key>` (or a
tinker session) reflects the new value; then separately confirm that
every `env()` call in the codebase lives inside a `config/*.php` file by
searching for `env(` outside that directory and getting zero results.
