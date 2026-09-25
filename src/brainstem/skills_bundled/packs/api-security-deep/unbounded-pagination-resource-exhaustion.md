---
name: unbounded-pagination-resource-exhaustion
description: A list endpoint's page size or offset parameter has no upper bound, letting one request force an enormous, resource-exhausting database query.
triggers: ["page size parameter causes server to hang", "requesting huge limit crashes API", "unbounded offset pagination slow query", "client can request unlimited records per page"]
permissions: ["READ"]
---

## Symptom
A list endpoint like `GET /orders?page_size=N` or `GET /items?limit=N&offset=M` responds fine for normal traffic, but a request with an extreme `page_size` (e.g. 1000000) or a very large `offset` on a big table causes a multi-second-to-multi-minute response, elevated database CPU, or a full request timeout/crash -- and because it's a single well-formed request, generic rate limiting doesn't flag it as abuse.

## Likely causes
1. **The endpoint uses the client-supplied limit/page_size directly in the query with no server-side maximum**, so `page_size=1000000` is passed straight to `LIMIT` with no clamping, and the database (and the serialization layer building the JSON response) does proportionally more work.
2. **Offset-based pagination degrades on large offsets regardless of limit** -- `OFFSET 5000000` still requires the database to scan and discard five million rows before returning results, so even a request with a small `limit` but a huge `offset` is expensive, and this cost scales with table growth even if nobody changes their query pattern (a slow-burn version of the same problem).
3. **No default limit is applied when the parameter is omitted entirely**, so a request with no pagination parameters at all returns the full table, and this "innocent" case is often missed during hardening because testing focuses on the explicit large-value case.
4. **Nested/included relations are expanded per row without their own limits** (e.g. `?include=comments` on a list endpoint returning thousands of parent rows, each eagerly loading its own child collection), multiplying the cost of an already-large page size by the size of each row's related data.

## Diagnose
- Send requests with progressively larger `limit`/`page_size` values against a staging environment with production-scale data and measure response time and database query duration -- identify the point at which cost stops being roughly linear (often indicating a full table scan or unindexed sort kicking in).
- Check the endpoint's parameter validation/schema for an explicit maximum on limit/page_size parameters, and check what happens when the parameter is omitted (confirm a sane default is applied, not "unlimited").
- Test large-offset requests specifically (`offset=1000000` with a small `limit`) and compare their latency to small-offset requests with the same limit -- a significant difference confirms offset-based pagination is the underlying mechanism, not just limit size.
- Check whether list endpoints that support `include`/`expand`/nested-resource parameters apply pagination or a hard cap to those nested collections independently, or just to the top-level list.

## Fix
Bound every dimension of pagination cost server-side, and prefer pagination strategies that don't degrade with table growth:
- Enforce a maximum `page_size`/`limit` server-side (reject or silently clamp requests above it, documented clearly either way) and apply a sensible default when the parameter is omitted -- never trust the client-supplied value directly in the query.
- For large, frequently-paginated tables, move from offset-based to cursor/keyset pagination (`WHERE id > last_seen_id ORDER BY id LIMIT n`), which has consistent cost regardless of how deep into the result set the client is paging, unlike `OFFSET` which must scan past all skipped rows.
- Apply the same limit/default rules to any nested/included collections returned alongside a list response, not just the top-level page size.
- Add a query cost or timeout guard at the database layer (statement timeout) as a backstop, so a pagination parameter that slips past application-level validation still can't run indefinitely against the database.

## Pitfalls
Don't fix only the `limit` parameter while leaving `offset` unbounded -- a request with a small, "safe-looking" limit and a huge offset can be just as expensive against a large table, and teams that test only the limit parameter often miss this because it doesn't look like the obvious abuse pattern.

## Verify
Against a staging database seeded to production scale, confirm a request with `page_size` above the configured maximum is clamped or rejected with a fast response, and confirm a request with a very large `offset` and small `limit` still completes within an acceptable latency bound (or is rejected/redirected to cursor-based pagination) rather than degrading linearly with table size.
