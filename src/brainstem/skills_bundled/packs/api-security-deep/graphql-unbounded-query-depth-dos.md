---
name: graphql-unbounded-query-depth-dos
description: A GraphQL API accepts arbitrarily deep or wide nested queries with no depth or complexity limit, letting one query trigger database-crushing load.
triggers: ["GraphQL query taking down the database", "deeply nested GraphQL query timeout", "GraphQL denial of service single query", "need query complexity limiting GraphQL"]
permissions: ["READ"]
---

## Symptom
A single GraphQL request -- sometimes from a legitimate client's buggy recursive fragment, sometimes from a deliberate attacker -- causes database CPU/connection pool exhaustion or the API process to OOM, while HTTP-layer rate limiting shows nothing unusual because it was literally one request. Query logs show deeply nested selections (e.g. `user { posts { comments { author { posts { comments { ... } } } } } }`) or extremely wide field selections repeated via aliases.

## Likely causes
1. **No query depth limit is enforced**, so a schema with circular relationships (user -> posts -> comments -> author -> posts -> ...) allows a client to nest selections to arbitrary depth, and each level of nesting multiplies the number of resolver calls/database queries geometrically.
2. **No query complexity/cost limit is enforced**, so even a shallow query can request thousands of fields or use field aliases to request the same expensive field hundreds of times in one request (`a1: expensiveField a2: expensiveField a3: expensiveField ...`), each incurring its own resolver cost.
3. **Resolvers don't batch or dataloader-cache**, so each nested level triggers N+1 database queries independent of GraphQL-layer limits -- meaning even moderate depth causes quadratic-or-worse query counts against the database.
4. **Introspection is left enabled in production** with no query allowlisting, giving an attacker the full schema (including expensive or internal fields) to design a maximally costly query without any prior knowledge of the API.

## Diagnose
- Check the GraphQL server setup for depth-limiting middleware (`graphql-depth-limit`, `graphql-query-complexity`, Apollo's `costAnalysis`, or equivalent for your server) -- if none is configured, this is the direct gap.
- Reproduce in a test environment: send a query nesting a circular relationship 10-15 levels deep and observe response time and resolver call count (enable resolver-level logging or a tracing extension) -- if the count grows exponentially with depth, there's no cost control.
- Check whether resolvers for one-to-many relationships use a batching/dataloader pattern or issue a fresh query per parent object; grep resolver code for direct ORM calls inside a resolver function that runs once per row of the parent field.
- Check whether introspection (`__schema`, `__type`) is queryable against the production endpoint without authentication -- if so, the full attack surface is discoverable with zero prior schema knowledge.

## Fix
Layer multiple GraphQL-specific controls rather than relying on general HTTP rate limiting:
- Enforce a maximum query depth at the GraphQL layer (reject queries exceeding a fixed depth, typically 6-10 depending on schema shape) using validation middleware that runs before execution, not after resolvers have already started work.
- Enforce a query complexity/cost budget: assign a cost to each field (higher for expensive/list-returning fields) and reject queries whose total statically-computed cost exceeds a threshold, so width-based attacks via aliasing are caught even at shallow depth.
- Use dataloader-style batching for all one-to-many resolvers so that even a legitimately deep/complex query results in batched, deduplicated database access instead of N+1 queries per level.
- Disable introspection in production (or gate it behind authentication for internal tooling only), and consider persisted-query allowlisting for public-facing GraphQL APIs so only pre-approved query shapes execute at all.

## Pitfalls
Don't rely on a request timeout alone as your DoS defense -- by the time a runaway query is killed by a timeout, it has often already consumed a database connection and significant CPU/IO, and an attacker can send several such queries concurrently faster than timeouts reclaim resources. Depth/complexity limits must reject the query before execution starts, not just bound how long execution is allowed to run.

## Verify
Add an automated test that submits a query exceeding the configured depth/complexity limit and asserts it's rejected at the validation stage (before any resolver executes -- check via resolver call count or tracing, which should be zero), and confirm legitimate, real-world query shapes used by your actual clients still pass under the configured limits.
