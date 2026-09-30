---
name: introspection-queries-overload-production-schema
description: A busy production GraphQL server experiences latency spikes or elevated CPU load specifically traceable to repeated full-schema introspection queries.
triggers: ["introspection query slow", "graphql schema query high cpu", "tooling hammering graphql introspection", "__schema query causing load", "introspection performance impact production"]
permissions: ["READ"]
---

## Symptom
Production monitoring shows periodic CPU or latency spikes on the GraphQL server that correlate with `__schema` / `__type` introspection queries in access logs, rather than with normal application query traffic -- a full introspection query walks and serializes the entire schema graph (every type, field, argument, and description string), which is a nontrivial, single-large-response computation distinct from a normal, bounded application query, and it's being run far more often, or by far more callers, than intended.

## Likely causes
1. **Introspection is left enabled and publicly reachable in production**, and one or more automated API-discovery/documentation tools, security scanners, or scheduled schema-sync jobs (from third-party integrations, internal tooling, or even hostile scanners) poll the full schema on a tight interval, each poll being an expensive whole-schema traversal rather than a cheap, bounded operation.
2. **A client-side developer tool (GraphiQL, Apollo Sandbox, a schema-aware IDE plugin) is configured to point at the production endpoint instead of a dedicated introspection/staging endpoint**, and it re-fetches the full schema on every page load or reconnect for every developer using it, multiplying an expensive query by however many people have the tool open.
3. **A CI/CD pipeline step re-fetches the live production schema via introspection on every build or deploy** (e.g. to regenerate typed client code) rather than caching the schema or fetching it from a schema registry/staging environment, turning a per-deploy cost into a recurring production load source correlated with deploy frequency.
4. **No dedicated caching exists for the introspection response specifically**, even though the schema itself changes rarely (only on deploy) -- so every introspection request pays the full traversal and serialization cost from scratch, when the vast majority of that work is identical response content on every single call it did seconds ago.

## Diagnose
- Filter access logs / APM traces specifically for operations matching `IntrospectionQuery` or containing `__schema`/`__type` as the root selection, and correlate their frequency and response time/CPU cost against the load spikes seen in monitoring.
- Identify the caller: check `User-Agent`, API key, or source IP on the flagged introspection requests to distinguish an internal tool misconfigured to hit prod, a legitimate but overly-frequent integration, or an external scanner with no relationship to your organization.
- Measure the actual cost of one introspection query directly (time a manual `curl` of the standard introspection query against production, or a staging replica) to quantify the per-call cost and multiply by observed call frequency to confirm it explains the observed load.
- Check whether introspection is gated behind authentication/authorization at all, or fully public -- an unauthenticated, unthrottled introspection endpoint has no natural ceiling on how often external parties can hit it.

## Fix
Treat introspection as a distinctly expensive, cacheable, and access-controllable operation rather than an always-on convenience:
- Cache the full introspection response server-side (it only needs to be recomputed when the schema itself changes, i.e. on deploy) and serve repeated identical introspection requests from that cache instead of re-traversing the schema graph every time -- most GraphQL server frameworks support this via a response cache keyed on the operation, or a manual cache invalidated on deploy.
- Disable introspection entirely on the public production endpoint (returning the standard "introspection disabled" behavior) and instead publish the schema through a dedicated, cached artifact -- a schema registry, a static SDL file, or a docs site generated at build/deploy time -- for legitimate consumers like client codegen and API documentation tools.
- If internal tooling or partner integrations genuinely need live introspection, put it behind its own authenticated endpoint or a separate lower-traffic instance, decoupled from the public application-query serving path, so its load (however frequent) can't compete with real user traffic.
- Apply per-client or per-IP rate limiting specifically to introspection-shaped queries (detectable by their root selection set) even if general application query rate limits are more permissive, since a legitimate low-volume client would rarely need more than one introspection call per schema version.

## Pitfalls
Disabling introspection everywhere without providing any alternative for legitimate client codegen and internal documentation tooling just relocates the pain -- developers will either re-enable it out of necessity (undoing the fix) or resort to manually copy-pasting a stale SDL file that drifts from the real schema; the fix needs a replacement distribution channel for the schema, not just a flag flip.

## Verify
After caching or disabling public introspection, replay the previously-identified high-frequency introspection traffic pattern against production (or a load-test replica) and confirm CPU/latency no longer spikes in correlation with it, while confirming legitimate schema consumers (codegen pipelines, internal docs) still successfully retrieve the schema through whatever replacement channel was put in place.
