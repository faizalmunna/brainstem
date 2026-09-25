---
name: local-emulator-hides-production-only-bugs
description: Local serverless emulation passes cleanly but the deployed function fails in production due to networking, cold-start, or resource-limit differences the emulator doesn't replicate.
triggers: ["works locally fails in lambda", "sam local works but deployed fails", "serverless offline different behavior production", "function works in emulator but not aws"]
permissions: ["READ"]
---

## Symptom
A function passes every test running under a local emulator (SAM CLI
`local invoke`, the Serverless Framework's `offline` plugin, Azure
Functions Core Tools, the GCP Functions Framework, or a Docker-based
Lambda runtime image run manually) and then fails, behaves differently, or
is unacceptably slow the moment it's actually deployed -- a VPC-attached
resource it can't reach, a cold start that takes seconds longer than
anything seen locally, a memory limit hit that never appeared in local
runs, or IAM permission errors that don't exist in the emulator because
the emulator doesn't enforce real permission boundaries.

## Likely causes
1. **The emulator runs the function's code with the local machine's
   networking and credentials**, not the actual deployed execution
   environment's network path (VPC subnets, NAT gateway, security groups)
   or its actual IAM role -- so a network path that's blocked in
   production (no route to a VPC-only resource) or a permission that's
   missing from the real execution role simply isn't exercised locally at
   all.
2. **Cold-start behavior is fundamentally different or absent locally** --
   a local emulator typically keeps the process warm across test runs and
   doesn't reproduce the actual runtime bootstrap, extension loading, or
   (for VPC-attached functions) ENI attachment latency that makes real
   cold starts slow, so a latency problem that only shows up on genuine
   cold starts is invisible in any local testing loop.
3. **Resource limits (memory, ephemeral disk, execution timeout) aren't
   enforced the same way locally** -- a local run often has access to the
   host machine's full memory and disk regardless of the configured
   function memory size, so a function that would OOM or run out of
   `/tmp` space in production runs fine locally simply because the limit
   isn't actually applied.
4. **The emulator's implementation of an event source is an approximation,
   not the real service** -- a local SQS/S3/EventBridge emulation may not
   reproduce actual retry timing, batch delivery semantics, or the exact
   event payload shape (including quietly missing or extra fields) that
   the real managed service sends, so handler code that works against the
   emulator's approximation can break against the real payload.
5. **Environment parity gaps in the runtime itself** -- a locally
   installed language runtime version, native binary architecture, or
   installed system library differs from the actual deployed runtime
   image, so a dependency with a native extension (a compiled Python
   wheel, a native Node module) that works locally fails to load in the
   real environment with an architecture or missing-library error.

## Diagnose
- Compare the exact runtime identifier and architecture (e.g., `x86_64` vs
  `arm64`, exact language minor version) configured for the deployed
  function against what's actually running locally -- a mismatch here
  directly explains native-dependency failures that don't reproduce
  locally.
- Check whether the failure only manifests on genuine cold starts in
  production (via the Init Duration metric and correlating failure
  timestamps with cold-start events) -- if so, treat "works in the
  emulator" as uninformative for this specific bug class, since most
  emulators don't reproduce cold-start conditions at all.
- Diff the actual event payload received in production (captured via a
  debug log of `event` on first entry to the handler) against the payload
  the local emulator generates for the same event type -- field-level
  differences explain "works in emulator, breaks in prod" for
  event-source-specific bugs.
- Check whether the function is VPC-attached and whether the failing
  behavior involves reaching another resource (RDS, ElastiCache, an
  internal API) -- local runs have no equivalent network boundary, so any
  bug involving reachability, security groups, or DNS resolution inside a
  VPC is structurally untestable in a plain local emulator.
- Deploy to a real (non-production) environment as the actual reproduction
  step rather than iterating further locally, once a local/production
  discrepancy is suspected -- a dev/staging AWS account with the same IAM
  role, VPC config, and runtime as production is the closest thing to a
  reliable local-equivalent test.

## Fix
Treat local emulation as useful for fast logic iteration but not as a
substitute for testing against the real platform for anything involving
networking, IAM, cold starts, or resource limits -- maintain a real
low-cost cloud dev/staging environment that mirrors production's VPC
config, execution role, memory/timeout settings, and runtime
architecture, and make deploying to it (not running the emulator) the
gating step before merging changes that touch those areas. Pin the local
development runtime version and architecture to exactly match the
deployed configuration (via the same container image used for deployment,
where the platform supports building/testing against that image directly)
rather than whatever happens to be installed on a developer's machine.
For event-source-specific logic, write tests against captured real event
payloads (recorded from actual production or staging traffic) rather than
hand-constructed or emulator-generated fixtures, since those are most
likely to drift from the real service's actual shape.

## Pitfalls
Over-correcting by testing every single change against a live cloud
environment adds deploy latency to the inner development loop and slows
iteration on pure logic changes that have nothing to do with networking or
platform limits -- the fix is knowing which class of bug the local
emulator can and can't catch, and reserving the slower real-environment
test for changes in the categories it can't (VPC, IAM, cold start,
resource limits, event source specifics), not abandoning local iteration
entirely. Also, "testing in production" as the de facto strategy because
staging was never kept in parity with production's VPC/IAM config just
moves the same gap one environment later without actually closing it.

## Verify
Deploy the change to a staging environment configured with the same
runtime architecture, VPC attachment, execution role, and memory/timeout
settings as production, force a genuine cold start (e.g., update an
environment variable to invalidate warm containers), and confirm the
specific behavior that diverged locally (a network call succeeding, a
resource limit not being hit, a native dependency loading) now matches
expectations before considering the fix validated.
