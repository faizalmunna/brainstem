---
name: dataloader-cache-serves-stale-data-across-mutations
description: A GraphQL query returns stale field values right after a mutation updated the same object within the same request or session.
triggers: ["dataloader returning old data after mutation", "graphql mutation response shows stale field", "dataloader cache not invalidated", "graphql stale read after write in same request"]
permissions: ["READ"]
---

## Symptom
A client calls a mutation that updates an object (e.g. `updateUser(id, { name })`), and the mutation's own response, or a subsequent query in the same request/session, still shows the pre-mutation value for that field -- even though the database was correctly updated. This is distinct from the classic N+1 problem: batching is working, but its per-request memoization cache is now the source of incorrect data rather than a performance win.

## Likely causes
1. **The DataLoader instance is request-scoped but the mutation resolver reads the same loader's cache after writing**, so the loader returns its memoized pre-mutation value instead of hitting the database again -- DataLoader caches by key for the lifetime of the instance, and a write doesn't automatically invalidate that cache.
2. **The DataLoader instance is accidentally scoped longer than one request** (e.g. instantiated at server startup or per-connection instead of per-request), so stale entries persist across multiple unrelated requests, not just within one mutation-then-query sequence.
3. **A mutation resolver writes via a different code path than the one the loader batches through** (e.g. writes go straight to the ORM while reads go through a cached repository layer), so nothing in the write path knows a loader cache entry exists to clear.
4. **GraphQL response shape returns the mutated object by re-fetching it through a field resolver that shares the same loader key**, and the loader's `.clear(key)` or `.prime(key, newValue)` call was never added when the mutation was implemented, because the original resolver was written before the loader existed.

## Diagnose
- Reproduce with a minimal sequence: run a mutation, then in the mutation's own return payload (or an immediately following query in the same request) check whether the returned field matches what was just written.
- Check whether the mutation resolver calls `loader.clear(id)` or `loader.prime(id, updatedValue)` after the write -- grep resolver code for the loader instance name near mutation handlers; its absence is the direct gap.
- Confirm loader scoping: check where the DataLoader (or equivalent batching cache) is instantiated -- it should be created fresh inside the per-request context factory, not at module/server scope. Log the loader instance's identity/memory address across two different requests to confirm they differ.
- If the app uses a caching layer beyond DataLoader (Redis, in-memory LRU) in front of resolvers, check whether that cache -- not just the loader -- was also cleared on write; multiple cache layers each need their own invalidation.

## Fix
Treat the batching loader as a cache that requires explicit invalidation on write, not just a performance optimization that's transparent to correctness:
- After any mutation that changes an object, call `loader.clear(id)` for every loader keyed on that object's ID before the resolver returns, or `loader.prime(id, newValue)` if you already have the fresh value and want to avoid a redundant re-fetch.
- Ensure the loader is constructed once per request (typically in the GraphQL context factory function that framework calls per-request) and never reused or cached across requests -- this eliminates the cross-request staleness case entirely and confines the invalidation problem to within a single request/mutation.
- Centralize write operations through the same data-access layer the loaders batch-read from, so there's one place responsible for both the write and the corresponding cache invalidation, rather than scattering ad hoc clear/prime calls across every mutation resolver.

## Pitfalls
Calling `loader.clear()` for the mutated object but forgetting related loaders that key on a different field of the same underlying data (e.g. clearing `userById` but not `userByEmail`, or not clearing a `postsByAuthorId` list loader when the author's posts count changed) leaves inconsistent partial invalidation that's harder to notice than a fully stale response, because some fields update and others don't.

## Verify
Write an integration test that performs a mutation and immediately queries the mutated field(s) in the same request context (reusing the same loader/context instance the way the real server does per-request), asserting the returned value matches the mutation's input rather than the pre-mutation database state.
