---
name: turborepo-cache-miss-diagnosis
description: Diagnose why Turborepo (or Nx) isn't hitting its build/task cache when nothing relevant appears to have changed, wasting CI time re-running unchanged work.
triggers: ["turborepo cache miss", "turbo cache not working", "nx cache not hitting", "monorepo rebuilds everything", "turbo full turbo not showing"]
permissions: ["READ"]
---

## Symptom
Turborepo (or Nx) re-runs a task (build/test/lint) from scratch even
though the relevant package's source hasn't changed since the last run
that should have cached it -- visible as the task missing the expected
`>>> FULL TURBO` (cache hit) output, or a much longer CI run than the
actual change should require.

## Likely causes
1. **A task's `inputs` (or default file-hashing scope) includes files
   that change on every run for unrelated reasons** -- a generated
   timestamp file, a lockfile that gets touched by tooling, or an
   overly broad glob that accidentally includes build output/node_modules
   -- so the cache key changes even when the meaningful source didn't.
2. **A task's `inputs` is too narrow**, missing a file that genuinely
   affects the task's output (a shared config file, an environment
   variable the build depends on), which can cause the opposite, more
   dangerous problem: a stale cache hit serving outdated output because a
   real change wasn't accounted for in the cache key.
3. **Environment variables affecting the build aren't declared** in the
   task's `env`/`passThroughEnv` configuration, so a change to an env var
   that actually affects output doesn't invalidate the cache (a
   correctness bug), or conversely the cache key includes irrelevant env
   vars that change every run (a cache-miss bug).
4. **Remote caching not configured or not authenticated in CI**, so every
   CI run starts from an empty cache even though a previous run (locally
   or in a prior CI job) already computed the same result.
5. **A task depends on another task's output (`dependsOn`) that itself
   isn't cached/hitting**, so the miss cascades even if the specific task
   in question would otherwise be cacheable.

## Diagnose
- Run with verbose/dry-run output (`turbo run build --dry=json` or
  equivalent) to see exactly what inputs/hash Turborepo computed for the
  task, and compare against the previous run's hash to see what changed.
- Check the `turbo.json` (or `nx.json`) task configuration for `inputs`,
  `outputs`, `env` declarations -- an overly broad or missing pattern is
  usually visible directly in the config once you're looking for it
  specifically.
- Check CI logs for remote cache authentication/configuration -- a
  silent auth failure can make remote caching a no-op without an obvious
  error, appearing identical to "cache always misses."
- For a `dependsOn` cascade, trace which upstream task actually missed
  first and treat that as the root cause, not each downstream miss
  independently.

## Fix
- Scope `inputs` precisely to files that actually affect the task's
  output -- exclude generated/timestamped files, and include shared
  config files the build genuinely depends on but that live outside the
  package's own directory.
- Declare environment variables that affect build output explicitly in
  the task's `env` configuration so the cache key correctly reflects
  them, and avoid depending on undeclared env vars inside build scripts.
- Set up and authenticate remote caching in CI (Vercel Remote Cache for
  Turborepo, Nx Cloud for Nx, or a self-hosted equivalent) so cache hits
  computed in one CI run (or locally) are available to subsequent runs,
  not just within a single machine's local cache.
- Fix the root-cause upstream task first when a `dependsOn` chain is
  cascading misses, rather than tuning every downstream task's
  configuration independently.

## Pitfalls
- Narrowing `inputs` too aggressively to force more cache hits can create
  a correctness bug: a real change to something excluded from `inputs`
  won't invalidate the cache, so a stale build gets served as if it were
  current -- err toward including anything the build might plausibly
  depend on, and verify precisely rather than guessing.
- Remote cache hits across environments (a different Node/OS version, a
  different lockfile state) that don't actually produce equivalent output
  is a correctness risk, not just a performance one -- ensure the cache
  key includes anything the build environment differs on that would
  affect output, or scope remote cache sharing to environments known to
  be equivalent.

## Verify
Make a no-op run (no source changes) and confirm the task now reports a
cache hit; then make a change specifically to a file that should
invalidate the cache and confirm it correctly misses -- checking both
directions, not just that hits now happen more often.
