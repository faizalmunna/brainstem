---
name: client-ignores-graphql-field-errors-checks-only-http-status
description: Client code treats a GraphQL response as successful because it returned HTTP 200 while the errors array actually reported a failed field or partial data.
triggers: ["graphql returns 200 but has errors", "client not handling graphql errors array", "partial data graphql error ignored", "graphql error swallowed silently by frontend"]
permissions: ["READ"]
---

## Symptom
A mutation or query fails at the field-resolver level (a validation error, a downstream service timeout, an authorization denial on one field) and the GraphQL server correctly returns HTTP 200 with an `errors` array alongside `data` (per spec, since a GraphQL response can be partially successful), but client code only checks `response.ok` / HTTP status code, sees success, and proceeds to use `data` as if the operation fully succeeded -- leading to null-reference crashes downstream, silently missing fields, or a mutation the user believes succeeded when it actually failed.

## Likely causes
1. **Client code was written by developers coming from a REST background** who reflexively check `if (response.status === 200)` as the success condition, because that pattern is correct for REST but incomplete for GraphQL, where 200 only means "the HTTP transport succeeded," not "the operation succeeded."
2. **The GraphQL client library is used at a low level (raw `fetch` to the `/graphql` endpoint) without a GraphQL-aware client (Apollo Client, urql, Relay) that surfaces the `errors` array as a first-class error state** -- hand-rolled fetch wrappers often parse `data` and never even look at `errors`.
3. **A field-level error produces `data.someField: null` with a corresponding entry in `errors`, and the client's rendering code treats `null` as "no data yet" (a loading state) or "empty" (an empty list/optional field) rather than "this field failed to resolve,"** conflating three semantically different states into one falsy check.
4. **Error handling was tested only against the happy path and against total request failure (network error, 500), never against the partial-failure shape** that GraphQL specifically introduces, so the untested code path silently ships.

## Diagnose
- Trigger a known field-level error in a test environment (query a field that requires permissions the test user lacks, or a field backed by a resolver you can force to throw) and inspect the raw HTTP response body -- confirm it's `200 OK` with a populated `errors` array and check what the client code actually does with that response.
- Grep client-side data-fetching code for `response.ok`, `response.status`, or HTTP-status-based branching used as the sole success signal for GraphQL calls, and cross-reference whether `errors` is ever read at all.
- If using a GraphQL client library, check whether its built-in error surface (Apollo's `error` field from `useQuery`/`useMutation`, urql's `error` in the result object) is actually being checked in the component/caller code, versus only `data` being destructured and used.
- For partial-failure cases, check whether the client's UI can distinguish "field is null because it's optional and legitimately empty" from "field is null because it errored" -- inspect whether `errors[].path` is ever cross-referenced against which fields came back null.

## Fix
Treat the GraphQL response contract as three-way (full success, partial success with errors, total failure) rather than binary HTTP success/failure:
- Always check the `errors` array on every GraphQL response regardless of HTTP status, and route error handling based on its presence/contents, not `response.status` -- a 200 with a non-empty `errors` array must be treated as at least a partial failure by calling code.
- Use a GraphQL-aware client library's built-in error state (rather than hand-rolled fetch parsing) so error surfacing is consistent across the app instead of reimplemented ad hoc per call site, and so partial-data-plus-error responses are modeled explicitly rather than collapsed into a single boolean.
- For mutations specifically, never treat a mutation as successful for user-facing purposes (toast, navigation, optimistic UI commit) without confirming `errors` is empty or absent, since a "successful-looking" 200 response with errors on a mutation is exactly the scenario where users lose data silently (e.g. believing a save succeeded when it didn't).
- Cross-reference `errors[].path` against the requested fields when rendering, so a null caused by a legitimate optional field is visually distinct from a null caused by a resolver error the user should be told about.

## Pitfalls
Wrapping every GraphQL error into a single generic "something went wrong" catch-all is itself an anti-pattern almost as bad as ignoring errors entirely -- GraphQL's `errors[].path` and `extensions.code` are specifically designed to let a client distinguish a validation error, an authorization error, and a downstream timeout, and collapsing all of them into one generic message throws away information that would let the UI degrade gracefully (e.g. show partial data with a retry affordance just for the failed field) instead of failing the whole view.

## Verify
Write a client-side test that mocks a GraphQL response with HTTP 200, a populated `errors` array, and `data` containing a null for the errored field, then assert the client's error-handling path is triggered (an error state is shown, a mutation is not treated as successful) rather than the happy path proceeding with the null value unchecked.
