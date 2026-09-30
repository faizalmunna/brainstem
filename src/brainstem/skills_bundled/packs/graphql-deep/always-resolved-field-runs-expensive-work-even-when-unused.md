---
name: always-resolved-field-runs-expensive-work-even-when-unused
description: A resolver performs a slow external call for a field included in nearly every client query even when that specific field is not actually requested.
triggers: ["graphql resolver runs even when field not selected", "expensive field slows down every query", "graphql over-fetching server side work", "resolver always calls external API regardless of selection set"]
permissions: ["READ"]
---

## Symptom
A GraphQL type has a field backed by an expensive operation (a call to a third-party API, a heavy computation, a cross-service RPC), and profiling shows that operation running on nearly every request to that type -- including requests whose selection set doesn't even include the field -- because the expensive work happens eagerly when the parent object is assembled, not lazily inside the field's own resolver.

## Likely causes
1. **The parent type's base resolver (or a data-loading service layer above GraphQL) eagerly fetches and attaches all fields' data when constructing the parent object**, before the GraphQL execution engine has even looked at the client's selection set -- common when a REST-era service layer was reused as-is under a GraphQL layer, since REST responses are typically all-fields-always.
2. **The expensive field's resolver function does the work directly instead of being written as a proper field resolver that GraphQL only invokes for selected fields**, e.g. the parent resolver calls `enrichWithExternalData(user)` internally and attaches the result to the parent object regardless of the query shape, rather than defining `User.externalData` as its own resolver that GraphQL calls conditionally.
3. **A batching/DataLoader pattern was applied to the field but the loader is primed/warmed unconditionally for every parent object** in a batch resolver, regardless of whether any object in that batch actually had the expensive field selected in the original query.
4. **The schema models the expensive data as a required (non-nullable, always-present) field on a widely-used type**, so the query planner and every client query touching that type ends up needing to resolve it whether or not the specific use case cares, because the type design itself doesn't allow "skip this."

## Diagnose
- Add resolver-level tracing (Apollo's tracing extension, or manual timing logs keyed by field path) and compare the expensive field's resolver invocation count against how often it actually appears in client query selection sets over the same period -- a large gap confirms eager evaluation.
- Check whether the expensive operation happens inside the specific field's resolver function or inside a shared parent-object-loading function that runs before GraphQL execution reaches field resolution -- grep for the external API call and trace it back to which resolver function contains it.
- Look at the field's schema definition for nullability and placement: is it modeled as a top-level required field on a hot type, forcing eager resolution, versus being nested behind a nullable, opt-in sub-object that's naturally more often unselected?
- Check DataLoader batch function bodies for unconditional priming of every parent ID in a batch, versus only loading IDs that were actually requested by a resolver call for that specific field.

## Fix
Restructure so expensive work runs only inside the field's own resolver, which the GraphQL execution engine only invokes for fields present in the client's selection set:
- Move the expensive operation out of any shared/eager parent-loading step and into a dedicated resolver function bound specifically to that field (e.g. `User.externalProfile: async (parent) => fetchExternalProfile(parent.id)`), relying on GraphQL's per-field resolution model, which by design does not call a field's resolver unless that field is selected.
- If the expensive data is still needed via a DataLoader for batching, only call `loader.load(id)` from within the specific field's resolver, not from a shared per-object setup step that runs regardless of selection -- this keeps batching efficient while preserving the "only run if selected" property.
- Where the same expensive underlying call also happens to be needed by multiple sibling fields, use request-scoped memoization (a plain per-request cache keyed by input, or a DataLoader) rather than duplicating the call, so selecting several related expensive fields together doesn't multiply the cost, while selecting none of them still triggers zero calls.
- Consider whether the field belongs on the type at all if it's rarely used but structurally expensive; a separate query or a differently-shaped type for the rare "enriched" use case can avoid coupling the common case's performance to a rare field's cost.

## Pitfalls
Adding a manual "does the query even ask for this?" check inside a shared eager-loading function (by inspecting `info.fieldNodes` or the GraphQL resolve info) as a patch, instead of restructuring the field as a proper lazy resolver, is fragile and hard to maintain -- it reimplements what the GraphQL execution engine already does for free when fields are structured correctly, and tends to bit-rot as the schema evolves and new call sites forget to add the same check.

## Verify
Send two versions of a query against the same type -- one selecting the expensive field, one omitting it -- with tracing/logging enabled, and confirm the expensive external call fires exactly once for the first request and zero times for the second, then confirm overall p95 latency for typical queries that don't need the field drops correspondingly.
