---
name: graphql-authorization-bypass-via-field-resolvers
description: A GraphQL API enforces authorization at the top-level query but individual field resolvers skip the check, letting nested traversal reach data the requester shouldn't see.
triggers: ["GraphQL nested field returns unauthorized data", "authorization check missing in resolver", "user can see other users data through relationship field", "GraphQL access control only on root query"]
permissions: ["READ"]
---

## Symptom
A top-level query like `getOrder(id)` correctly checks that the requesting user owns that order, but a query that reaches the same underlying data through a different path -- e.g. `me { organization { allOrders { customer { email, paymentMethods } } } }` or traversing from an object the user does legitimately own into a related object they don't -- returns data belonging to other users or tenants, because the nested field resolvers never re-check authorization; they trust that reaching this point in the graph implies permission.

## Likely causes
1. **Authorization is implemented only at the root query/mutation level** (a decorator or middleware on the resolver map's top-level entries), while nested field resolvers that fetch related objects (`order.customer`, `team.members`, `post.author.email`) assume the parent object's authorization already covers them, which is false whenever the relationship crosses an ownership/tenant boundary.
2. **The schema exposes a relationship that was designed for internal/admin tooling** (e.g. `user.internalNotes` or `organization.allInvoices`) and reused in a public-facing schema without adding a field-level guard, because it "worked" in the admin context where the caller was already privileged.
3. **Batched/dataloader resolvers fetch data in bulk across the whole request** for efficiency, and the authorization check that used to happen per-row in a REST handler was dropped during the migration to GraphQL's batched resolution model.
4. **Union/interface types return a field is present on multiple concrete types with different sensitivity**, and the resolver applies one generic authorization rule that's correct for one type but not the other, so querying through the interface bypasses the stricter type-specific check.

## Diagnose
- Map the schema's authorization coverage: list every resolver (root and field-level) and check off which ones have an explicit authorization call versus which ones assume the parent resolver already authorized access -- any nested resolver returning data owned by a different principal than the root query's subject is a candidate gap.
- Write a test query that traverses from an object the test user legitimately owns into a relationship that should be restricted (e.g. from `me` to a colleague's private fields via a shared team/org edge) and check whether the response includes data it shouldn't.
- Check dataloader/batch-resolver implementations for a `WHERE owner_id = ?` or equivalent scoping clause -- if the batch loader fetches by ID list only, without also filtering by the requesting user's access rights, authorization has been silently dropped in the batching layer.
- Grep the resolver map for field resolvers on sensitive types (`email`, `paymentMethod`, `ssn`, `internalNotes`) and confirm each one independently verifies the current user's permission to view that specific field on that specific object, not just that a query executed successfully.

## Fix
Push authorization down to the field/object level rather than trusting the root query to cover the whole graph:
- Implement authorization as a reusable check invoked at each resolver that returns sensitive or cross-tenant data (e.g. a `canView(currentUser, targetObject)` function called inside `order.customer`, not just inside `getOrder`), so authorization travels with the data regardless of the path used to reach it.
- When using dataloaders/batching for performance, scope the underlying query itself to the requester's access rights (filter by tenant/owner in the batch-fetch SQL) rather than fetching everything and hoping a later check catches unauthorized rows -- unscoped batch fetches are also a data-leak risk independent of authorization if caching layers ever get confused about per-request scope.
- For schema fields shared between admin and public contexts, use distinct field-level directives or separate types (`PublicUser` vs `AdminUser`) instead of one type with a runtime "if admin, show more" branch that's easy to miss on a new field.
- For union/interface types, apply authorization checks at the concrete-type resolver level, not the interface level, so each type's sensitivity is independently enforced.

## Pitfalls
Don't assume that because the root query has an `@auth` directive, the whole response tree is safe -- GraphQL's resolver model means every field is independently executable, and a directive on the root field says nothing about what a child resolver does with the data it fetches. This is the single most common GraphQL-specific authorization gap and is distinct from generic broken access control because it's about resolver composition, not endpoint-level access.

## Verify
For each relationship in the schema that crosses an ownership or tenant boundary, write an integration test authenticated as User A that queries through User B's object graph and assert every field along that path either errors or returns null/redacted data, then confirm the same query authenticated as the legitimate owner returns full data.
