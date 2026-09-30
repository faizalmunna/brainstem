---
name: federated-query-plan-fans-out-into-excessive-subgraph-calls
description: A single client query against a federated GraphQL gateway triggers many more subgraph-to-subgraph round trips than the query's apparent complexity suggests.
triggers: ["federation query plan too many subgraph calls", "apollo gateway slow query plan", "federated graphql high latency single query", "entity resolution causing extra subgraph fetches"]
permissions: ["READ"]
---

## Symptom
A client sends what looks like a modest query against a federated gateway (Apollo Federation, or similar supergraph composition), but the gateway's query plan fans out into many sequential or semi-sequential subgraph requests, and end-to-end latency is dominated by network round trips between the gateway and subgraphs rather than by any single subgraph's own processing time -- visible in the gateway's query plan trace as many separate "fetch" nodes, several of them dependent on the previous one's result (waterfalling) rather than running in parallel.

## Likely causes
1. **An entity is spread across many subgraphs, each contributing just one or two fields**, so resolving a type with fields from four different subgraphs requires the query planner to issue a `_entities` resolution call to each of those four subgraphs for the same set of keys, turning one logical object fetch into four network round trips even though each individual subgraph call is fast.
2. **A field in one subgraph depends on the *output* of a field from another subgraph as an input** (e.g. subgraph B's resolver needs a value only subgraph A can supply), forcing the query planner to sequence the two fetches instead of parallelizing them -- this dependency chain compounds with nesting, since each additional dependent hop adds another full network round trip to total latency.
3. **A list field's per-item nested field pulls from a different subgraph than the list itself**, so federation's entity resolution has to batch-fetch that nested field's subgraph for every item in the list via `_entities`, and if that nested field itself has another cross-subgraph dependency, the fan-out compounds multiplicatively with list size, similar in shape to N+1 but happening at the network topology level between services rather than between the resolver and a single database.
4. **The subgraph boundary lines were drawn around team/ownership boundaries rather than around data-locality or access-pattern boundaries**, so commonly-co-queried fields (e.g. a product's price and its inventory count) live in different subgraphs purely because different teams own them, guaranteeing every product query pays a cross-subgraph round trip regardless of how the client structures its query.

## Diagnose
- Pull the gateway's query plan for the slow operation (Apollo Gateway/Router exposes this via `--explain` tooling, Studio's query plan visualizer, or a debug header) and count the number of `Fetch` nodes and, critically, how many are nested under `Sequence` (dependent, serialized) versus `Parallel` (independent, concurrent) -- sequential fetch chains are the direct latency driver, not fetch count alone.
- For each `Sequence`-nested fetch, identify what data it depends on from the prior fetch; this reveals which specific field's resolver in one subgraph requires a value computed or fetched by another subgraph, which is the actual coupling causing the wait.
- Measure per-fetch-node latency versus total request latency: if the sum of individual fetch latencies is much less than total request time, the gap is round-trip/serialization overhead from the fan-out itself, not slow subgraph processing -- pointing at plan shape as the fix target, not any one subgraph's performance.
- Review the subgraph ownership map for the specific type causing fan-out and check whether the fields commonly requested together in real client queries (from actual operation telemetry) are split across subgraph boundaries more than necessary.

## Fix
Reduce cross-subgraph round trips by addressing plan shape and boundary design, not just by tuning any single subgraph's speed:
- Where a dependent (`Sequence`) fetch chain exists because one subgraph's field needs another's output, evaluate whether that data dependency can be restructured -- e.g. by having the client pass the needed value directly as a query argument instead of requiring the gateway to fetch-then-forward it, collapsing a two-hop sequence into two independent parallel fetches.
- For entities heavily fragmented across many subgraphs, consider consolidating fields that are near-always queried together into fewer subgraphs (accepting some cross-team schema coordination cost) specifically for hot-path types identified via query plan analysis, rather than optimizing purely for team ownership independence.
- Use `@requires`/`@provides` federation directives deliberately to let a subgraph fetch a field it needs from another subgraph's data in the same resolution pass where possible, reducing the number of distinct round trips versus a naive full re-fetch.
- For list-based fan-out into a different subgraph per item, ensure the federation entity resolution is genuinely batching all items in the list into a single `_entities` call to the target subgraph (this is federation's default representation-batching behavior) rather than accidentally issuing one call per item due to a custom resolver bypassing standard entity resolution.

## Pitfalls
Chasing this purely by adding caching at each individual subgraph doesn't address a genuinely sequential dependency chain in the query plan -- caching reduces the cost of each hop's work but not the number of network round trips or their sequencing, so latency dominated by round-trip count (not per-hop compute time) requires fixing the plan shape or subgraph boundaries, not just making each subgraph respond faster.

## Verify
Re-generate the query plan after the fix and confirm the previously `Sequence`-nested fetch nodes are now `Parallel` (or eliminated entirely), then re-run the same client query end-to-end and confirm total latency drops by roughly the sum of the round trips removed, not just by each individual subgraph's own processing time improving.
