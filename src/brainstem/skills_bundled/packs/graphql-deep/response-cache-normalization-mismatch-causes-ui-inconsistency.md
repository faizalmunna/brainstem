---
name: response-cache-normalization-mismatch-causes-ui-inconsistency
description: A client-side GraphQL cache shows different, inconsistent values for the same underlying object across different views of an app after a partial update.
triggers: ["apollo cache showing stale data in one component", "graphql normalized cache inconsistent between views", "urql cache not updating all instances of object", "client cache object identity mismatch graphql"]
permissions: ["READ"]
---

## Symptom
After a mutation or a refetch updates an object's field in one part of a client application (e.g. a list view showing `Post.likeCount`), a different view rendering the same logical object (e.g. a detail page for that same post) continues to show the old value, even though both views are using the same GraphQL client and the same normalized cache -- the two views have silently diverged on what should be a single source of truth for the same entity.

## Likely causes
1. **The object lacks a stable, consistent cache key across the two queries**, because one query's response for the type doesn't include the field the cache normalizer uses for identity (commonly `id` or `__typename` + `id`) -- if one query selects `id` and the other doesn't, the normalized cache can't recognize they refer to the same entity and stores two separate, unlinked copies.
2. **A custom type policy / cache key function is inconsistent between different parts of the schema**, e.g. one type uses a composite key (`orgId:userId`) intentionally, but a related query path returns the same conceptual entity keyed only by `userId`, so the cache treats them as different objects even though the server considers them the same entity.
3. **The mutation's response payload doesn't return the updated object in a shape the cache can automatically merge**, so the cache either doesn't know to update the entity at all (client only updates its own local optimistic-response cache entry, not the normalized shared one) or requires a manual cache-update function that wasn't written to also patch every field affected, only the one the mutation's author was thinking about.
4. **Pagination or list-specific caching (e.g. Apollo's field policies for paginated lists) stores list-page data denormalized from item data**, so an item mutated via its normalized entity entry updates correctly wherever the entity is referenced directly, but a separately-cached list page holding an embedded copy of that item's fields doesn't get the update propagated to it.

## Diagnose
- Inspect the client cache's internal normalized store directly (Apollo Client DevTools' Cache tab, urql's Graphcache inspector) after triggering the divergence, and check whether there are two separate entries for what should be the same entity, versus one entry that's correctly shared but just not re-rendering.
- Compare the exact selection sets of the two queries feeding the two divergent views -- specifically check whether both include the fields the cache uses for normalization (`id`, `__typename` by default in most clients) consistently.
- Check any custom `typePolicies`/key-generation configuration for the entity's type and confirm it produces the identical key string for both query shapes involved (log or unit-test the key function directly with sample data from both queries).
- If a mutation is involved, inspect its response payload and any manual cache-update logic (`update` function in Apollo, `updates` config in urql) to confirm it actually writes to the same normalized cache key that the read-side queries reference, rather than only updating query-local state.

## Fix
Make entity identity consistent and explicit across every query and mutation touching that type, rather than relying on default behavior holding everywhere:
- Ensure every query and mutation response selects the fields the cache's normalization strategy needs for identity (`id` plus `__typename` at minimum) on every occurrence of the type, even when the calling code doesn't otherwise need those fields, specifically so the cache can recognize shared identity.
- For entities with legitimately non-trivial identity (composite keys, or types normalized differently in different contexts), define and use one explicit, centralized type policy / key function referenced consistently by all queries against that type, rather than letting default per-query behavior diverge silently.
- Ensure mutations return enough of the updated object (via the mutation's selection set) for the client's automatic cache normalization to update the shared entity entry directly, and where a list/pagination field can't automatically pick up entity-level changes, write an explicit cache-update function that patches the specific denormalized list-level copies too, not just the canonical entity entry.
- Where feasible, prefer normalized entity references over embedding full field copies in paginated/list-specific cache structures, so an entity update naturally propagates everywhere it's referenced instead of requiring the app to manually track every denormalized copy.

## Pitfalls
Working around the symptom with a manual `refetchQueries` call after every mutation (blindly re-fetching every view that might show the entity) instead of fixing the underlying identity/normalization mismatch treats the visible symptom while leaving the cache's actual entity-identity bug in place -- it papers over one specific divergence while the same root cause will resurface the next time a new view or mutation touches the same type.

## Verify
Render two different views/queries that both include the same entity in a test environment, trigger a mutation that updates a field on it, and assert both views' rendered output update to the new value without either view issuing an explicit manual refetch -- confirming the update propagated through normalized cache identity rather than coincidental re-fetching.
