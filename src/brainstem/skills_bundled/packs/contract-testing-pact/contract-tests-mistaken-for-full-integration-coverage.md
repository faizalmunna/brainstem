---
name: contract-tests-mistaken-for-full-integration-coverage
description: A team relies on passing consumer-driven contract tests as proof the whole integration works and skips real end-to-end integration testing, missing bugs contracts can't catch.
triggers: ["pact tests pass but integration still broken in staging", "contract testing replaced integration testing and bugs slipped through", "team thinks pact coverage means no need for e2e tests", "bug pact testing was never meant to catch"]
permissions: ["READ"]
---

## Symptom

All relevant Pact contracts are green, `can-i-deploy` approves the
release, yet a real end-to-end flow through staging or production still
breaks -- multiple services individually honor their pairwise contracts,
but the overall flow fails due to something no single contract could
express: wrong business logic across a multi-step workflow, a
timing/ordering issue across three or more services, an infrastructure
problem (DNS, TLS, load balancer routing), or a shared downstream
dependency (a queue, a cache) behaving unexpectedly under real load. The
team is confused because "the contract tests said this was fine."

## Likely causes

- **The team stopped writing or maintaining real end-to-end/integration
  tests after adopting contract testing**, treating pairwise contract
  verification as a full substitute, when contract tests by design only
  verify the shape and basic semantics of one request/response pair in
  isolation, never a multi-hop business flow.
- **The bug lives in logic that spans more than two services** (A calls B
  which calls C, and the bug is in how A's data flows through B's
  transformation into what C receives), which no single consumer-provider
  contract pair can capture since each contract only covers one edge of
  that chain.
- **The bug is environmental/non-functional** (network policy, service
  discovery misconfiguration, a certificate expiring, insufficient
  timeout budgets under real latency) -- categories of failure contract
  tests, which typically run in-process or against a mocked transport,
  are structurally unable to catch.
- **The bug is in emergent behavior under concurrency or real data
  volume** (a race condition between two consumers of the same provider,
  a cache stampede, an N+1 pattern only visible with realistic data
  sizes) that a single-interaction contract test, run in isolation with
  synthetic example data, was never testing for.

## Diagnose

1. Classify the actual bug: is it a mismatch in what one specific request/
   response pair looks like (a contract-testable class of bug), or does
   it require several services in sequence, real infrastructure, or real
   concurrency/scale to reproduce? Write down explicitly which category
   it falls into before deciding what kind of test would have caught it.
2. Check whether the project has any suite left that exercises the full
   deployed flow across real (or realistically staged) service instances
   -- if the answer is "we replaced that with Pact," that confirms the
   root cause rather than a gap in any specific contract.
3. Review the incident against the multi-service flow diagram (or trace
   data, if tracing is set up) to identify exactly which hop or
   cross-service interaction the bug actually occurred in, and confirm no
   pairwise contract between those two services was even asserting on
   the relevant behavior.
4. Ask whether the bug involved timing, load, or infrastructure at all --
   if so, that's independent confirmation this was never in scope for
   contract testing regardless of how well-written the contracts are.

## Fix

Keep a right-sized layer of real end-to-end/integration tests alongside
contract tests rather than replacing one with the other -- contract
testing's value is fast, isolated, per-edge verification that scales
well and avoids the flakiness of full integration environments; it
trades away exactly the cross-service, infrastructure, and concurrency
coverage that a smaller number of true end-to-end tests (or structured
staging smoke tests, or chaos/load testing where relevant) are meant to
provide. Decide deliberately, as a team, which categories of bug each
layer is responsible for catching, and keep enough of the expensive layer
to cover the categories contract tests structurally cannot -- not
"as many as we can afford," but specifically covering the multi-hop and
non-functional risk that's been identified as present in the system.

## Pitfalls

Don't respond to this kind of incident by trying to make contract tests
"catch everything" by inflating individual contracts to encode multi-
service business rules or environmental assumptions they weren't
designed to hold -- that makes contracts brittle, coupled to
implementation details beyond the immediate consumer-provider pair, and
harder to maintain, without actually closing the structural gap. The fix
is adding the right complementary test layer, not stretching contract
testing past its designed scope.

## Verify

For the specific incident, write (or restore) an end-to-end test that
exercises the real multi-service flow (or the specific non-functional
concern involved) and confirm it fails against the pre-fix state and
passes after the fix, while contract tests for the individual pairs
remain unchanged and still green throughout -- this demonstrates the two
layers are covering genuinely different risk, not duplicating each
other. Document in the team's testing strategy which layer is
responsible for this class of bug going forward, so the same gap isn't
reintroduced under time pressure.
