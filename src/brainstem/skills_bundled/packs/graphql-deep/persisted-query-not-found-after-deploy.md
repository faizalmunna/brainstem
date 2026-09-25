---
name: persisted-query-not-found-after-deploy
description: Clients running an older or newer build than the server start receiving PersistedQueryNotFound errors for queries that worked fine before a deploy.
triggers: ["PersistedQueryNotFound error", "persisted query allowlist mismatch", "graphql query hash not found after deploy", "automatic persisted queries failing production"]
permissions: ["READ"]
---

## Symptom
After a deploy of either the client app or the GraphQL server, some fraction of requests start failing with a `PersistedQueryNotFound` (or equivalent allowlist-rejection) error for queries that are otherwise valid and were working moments before -- often affecting only some users, correlated with which build of the client they have cached in their browser or app store version, not with anything wrong in the query itself.

## Likely causes
1. **The server's persisted query manifest (the allowlist mapping hash to query text) was regenerated and redeployed at the same time as, but not perfectly synchronized with, the client bundle**, so during the rollout window (or indefinitely, if a CDN/browser is caching an old client bundle) some clients send hashes the current server manifest doesn't recognize.
2. **Automatic Persisted Queries (APQ) rely on the server caching a hash-to-query mapping the first time a client sends the full query alongside its hash, but that cache was cleared or is not shared across server instances** (e.g. an in-memory APQ cache with no shared Redis backing behind a multi-instance/autoscaled deployment), so a request landing on a different instance than the one that originally cached the hash gets `PersistedQueryNotFound` even though another instance knows it.
3. **A strict (non-automatic) persisted query allowlist is generated from the client codebase at build time and deployed as a static manifest to the server, but the client and server deploy pipelines are decoupled**, so a client build ships before its corresponding server-side manifest update goes live, or vice versa -- a versioning/ordering problem between two independently deployed artifacts.
4. **Old client bundles remain in circulation longer than expected** (browser HTTP cache, a mobile app version users haven't updated, a service worker serving a stale JS bundle) and continue sending hashes for query shapes that were removed from the allowlist when the corresponding client code was assumed retired.

## Diagnose
- Check the error rate's correlation with client version: log the client build/version alongside `PersistedQueryNotFound` errors and confirm whether failures cluster on a specific old or new client version rather than being random.
- For APQ specifically, check whether the hash-cache backing store is shared across all server instances (Redis, Memcached) versus per-instance in-memory -- if per-instance, reproduce by sending the same "new" hash+query pair repeatedly to different instances behind the load balancer and checking if some instances 404 while others succeed.
- For strict allowlist mode, diff the currently-deployed server manifest against the hash the failing client is sending -- confirm whether that hash exists in the manifest at all, and check deploy timestamps of the client bundle versus the server manifest to establish ordering.
- Check whether a CDN or service worker is serving a stale client bundle: force-reload the affected client, or check `Cache-Control`/service-worker cache versioning on the JS bundle serving the query definitions.

## Fix
Design the persisted-query pipeline so client and server rollout order can never desynchronize into a hard rejection:
- For strict allowlists, deploy the server-side manifest update *before* the corresponding client build goes live (server change is backward-compatible-safe: it can recognize a new hash the old client never sends yet), and never remove old-but-still-possibly-in-use hashes from the manifest until confident via telemetry that no client is still sending them.
- For APQ, back the hash cache with a shared store (Redis) across all server instances rather than in-process memory, so any instance can resolve a hash that any other instance has already learned, eliminating the instance-affinity failure mode entirely.
- Version the persisted query manifest itself and have the server accept a grace-period window of the last N manifest versions rather than only the current one, cushioning against client bundles that are slightly behind due to caching or staged rollouts.
- On `PersistedQueryNotFound`, have API-aware clients (Apollo Client and similar do this by default for APQ) fall back to sending the full query document once, allowing the server to register it, rather than treating the first miss as a hard failure the user sees.

## Pitfalls
Assuming APQ's automatic fallback (client resends the full query on a miss) makes hash-cache synchronization a non-issue is a mistake for strict, security-motivated allowlists specifically -- strict mode exists to reject arbitrary query documents the server hasn't pre-approved, so silently falling back to accepting the full query defeats the point of using an allowlist in the first place; the fix must be operational (deploy ordering, shared cache) not "just let it fall back."

## Verify
Simulate a rolling deploy in staging: deploy the new server manifest first, confirm old clients still succeed against it, then deploy the new client build and confirm it succeeds too, with zero `PersistedQueryNotFound` responses logged across the transition window; for APQ, load-test with requests round-robined across multiple server instances and confirm a hash registered via one instance resolves successfully on all others.
