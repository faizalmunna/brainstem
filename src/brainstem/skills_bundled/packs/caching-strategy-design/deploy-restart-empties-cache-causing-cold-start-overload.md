---
name: deploy-restart-empties-cache-causing-cold-start-overload
description: Every deployment or process restart wipes the in-memory or newly-provisioned cache, causing a spike of simultaneous cache misses that overloads the backing store right after each release.
triggers: ["backend falls over right after every deploy", "database CPU spikes immediately after we release", "errors right after restart that go away on their own after a few minutes", "cold cache after deploy causing timeouts"]
permissions: ["READ"]
---

## Symptom
Immediately after a deployment or rolling restart, the backing database or upstream service sees a sharp latency and load spike — sometimes enough to trigger timeouts, error-rate alerts, or even cascading failures — that then subsides on its own within a few minutes without anyone intervening. The pattern is reliably correlated with deploy timestamps, and the team has learned to "just wait it out" or has started scheduling deploys for low-traffic windows to reduce the blast radius, without addressing the underlying cause.

## Likely causes
1. **In-process/in-memory cache is wiped by definition on every restart** (it lived in the process's memory), and every instance restarting during a rolling deploy hits the backing store cold at roughly the same time, with no mechanism to pre-populate before traffic arrives.
2. **A shared external cache (Redis/Memcached) is fine and persists across app restarts, but a deploy also recycles or flushes it** — a deploy step that includes `FLUSHALL`/cache-clear "to be safe," or a new cache cluster provisioned per environment/version instead of reused, has the same cold-start effect as an in-memory cache.
3. **New instances start receiving production traffic before any warming step runs**, because the load balancer/orchestrator's health check only verifies the process is up, not that its cache (or connection pools) are populated — "ready" and "warm" are treated as the same thing when they aren't.
4. **Cache key scheme changed in the deploy** (a version bump embedded in the key, a schema change to cached objects) so even a persistent, unflushed cache is effectively cold because the new code can't find its old keys — this looks identical to a full flush from the outside.
5. **All instances restart within a short window** (e.g., a deploy strategy that replaces most or all capacity near-simultaneously rather than truly incrementally) so there's no warm capacity left to absorb load while cold instances catch up.

## Diagnose
1. Overlay a graph of backing-store load/latency against deploy timestamps for the last several releases to confirm the correlation is consistent, not coincidental with something else that happens to run around deploy time (e.g., a cron job).
2. Check whether the cache layer in question is in-process (dies with the process) or external/shared (survives restarts) — this determines whether the fix is about warming or about not flushing. Check deploy scripts and infra-as-code for any explicit cache-clear/flush step.
3. If using an external cache, check whether the deploy provisions a new cache instance/cluster per release (common with some managed-cache-per-environment IaC patterns) rather than reusing the existing one — a new endpoint or cluster ID is a full cold start even though "the cache" nominally still exists.
4. Diff the cache key scheme between the previous and new release for any embedded version strings, serialization format changes, or renamed fields that would silently orphan the previously-warm keys.
5. Check the deployment strategy's concurrency (how many instances/percentage of capacity are replaced at once) and the health check definition (does it gate only on process liveness, or on some warmth signal) in the orchestrator config.

## Fix
For in-process caches, add an explicit warming step that runs before an instance is marked ready to receive traffic — prefetch the known hot keys (from a static list, from the previous instance's top-N access log, or by replaying a sample of recent real traffic against the new instance) as part of startup, and gate the readiness/health check on warming having completed, not just the process being up. For external/shared caches, ensure the deploy process never flushes them and that infrastructure changes (config updates, cache resizing) reuse the existing instance rather than provisioning a fresh one whenever avoidable. Roll deploys incrementally (a small percentage of instances at a time) so warm capacity from not-yet-replaced instances continues absorbing load while new instances warm up, rather than replacing most capacity simultaneously. If key-scheme changes are unavoidable, consider a transition period where both old and new key formats are checked/written to avoid a full cold start on that specific release.

## Pitfalls
Don't "fix" this by just throttling or rate-limiting the backing store during the cold-start window — that converts an overload into user-facing errors/latency on a schedule, which is more predictable but not actually solved. Also beware over-aggressive warming that itself causes a thundering-herd effect on the backing store (all new instances independently prefetching the same large hot-key list simultaneously) — stagger or coordinate warming across instances, or warm from a shared snapshot, rather than having every instance independently hammer the backing store on startup.

## Verify
Deploy to a staging environment configured with production-like cache size and traffic replay, and graph backing-store load through the deploy window before and after adding the warming step — confirm the post-deploy load spike is materially reduced or eliminated, and confirm via the readiness check logs that instances aren't receiving live traffic until warming has actually completed, not just started.
