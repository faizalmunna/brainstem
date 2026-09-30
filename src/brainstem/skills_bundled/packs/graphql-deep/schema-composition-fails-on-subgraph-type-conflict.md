---
name: schema-composition-fails-on-subgraph-type-conflict
description: A federated or stitched GraphQL gateway refuses to start or serve any traffic because two subgraphs define a conflicting shape for the same named type.
triggers: ["federation composition error", "schema stitching type mismatch", "gateway fails to start graphql federation", "supergraph composition failed", "subgraph type conflict"]
permissions: ["READ"]
---

## Symptom
The gateway (Apollo Federation, GraphQL Mesh, or a hand-rolled schema-stitching layer) fails composition at startup or deploy time with an error naming a type or field that "does not match" or "is defined with a different shape" across subgraphs, and the entire gateway is down -- not just the query paths touching that type -- because composition is all-or-nothing: if the supergraph schema can't be built, no query can execute against any subgraph.

## Likely causes
1. **Two teams independently defined a type with the same name but different fields or scalar types** (e.g. one subgraph's `Money` is a `Float`, another's is a custom `Money` object with `amount`/`currency`), which is a natural consequence of independently deployed subgraphs with no shared schema registry review process.
2. **A `@key` directive (federation entity key) is inconsistent between the owning subgraph and a subgraph extending that entity** -- e.g. the owning subgraph keys `Product` by `id`, but an extending subgraph declares `@key(fields: "sku")`, and the gateway can't resolve how to join the two representations of the same entity.
3. **A field was renamed or retyped in one subgraph without coordinating the change with other subgraphs that reference or extend the same type**, so composition that worked yesterday breaks today purely from an independent, unreviewed deploy in one service.
4. **Enum value sets diverge between subgraphs** that both contribute values to the same shared enum, and federation's enum-merging rules (intersection vs union, depending on usage as input vs output type) reject the mismatch silently until composition time, not at either subgraph's own build time.

## Diagnose
- Read the exact composition error message from the gateway/build tool -- Apollo's `rover subgraph check` or `rover supergraph compose` output names the specific type, field, and the two conflicting subgraphs verbatim; don't guess, the tool tells you exactly where the conflict is.
- Run schema composition as a standalone step in CI *before* deploying either subgraph (`rover supergraph compose --config supergraph.yaml` or equivalent), against the currently-published schema of every other subgraph, so a conflict is caught pre-merge instead of at production gateway restart.
- Diff the conflicting type's SDL definition between the two subgraphs directly (pull each subgraph's schema via introspection or its published SDL) to see the exact field/type/directive mismatch side by side.
- Check whether the two subgraphs were deployed independently and recently -- correlate deploy timestamps with when composition started failing to identify which side introduced the breaking change.

## Fix
Treat cross-subgraph schema composition as a governed contract, not an emergent property of independent deploys:
- Run schema composition checks in each subgraph's CI pipeline against the live/staged versions of all other subgraphs before merge (Apollo's schema registry + `rover subgraph check` model, or an equivalent composition dry-run for other federation/stitching tools), so conflicts are caught before a bad schema is even deployable, not after the gateway is already down.
- For entities shared across subgraphs, designate one subgraph as the canonical owner of the type's core shape and `@key`, and require other subgraphs to extend it via federation's `@extends`/`@external` mechanics rather than redefining overlapping fields independently.
- For shared enums or scalars, maintain them in a common schema fragment or shared package that every subgraph imports, rather than each subgraph hand-declaring its own copy that can drift.
- Roll out breaking subgraph schema changes behind a composition check gate in the deploy pipeline itself (block the deploy, not just warn) so an incompatible subgraph schema can never reach the point of being composed into the live supergraph.

## Pitfalls
Fixing the immediate conflict by manually editing the gateway's composed supergraph schema (if your tooling allows a manual override) instead of fixing the underlying subgraph SDL is a trap -- the next automatic composition run (on the next deploy of either subgraph) will regenerate the conflict, because the actual subgraph schemas were never reconciled, only the symptom was patched at the gateway layer.

## Verify
Re-run the composition step in CI (`rover supergraph compose` or equivalent) against both subgraphs' current schemas and confirm it succeeds with zero errors, then deploy to a staging gateway and execute a query that spans both previously-conflicting subgraphs' contributions to the shared type, confirming the response resolves fields from both sources correctly.
