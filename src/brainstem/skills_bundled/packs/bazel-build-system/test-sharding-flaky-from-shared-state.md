---
name: test-sharding-flaky-from-shared-state
description: Bazel test sharding produces intermittent test failures because test cases assigned to different shards share mutable external state that wasn't isolated per shard.
triggers: ["bazel test sharding flaky", "test shard count changes results", "bazel parallel test shared state", "sharded tests interfere with each other"]
permissions: ["READ"]
---

## Symptom

A test target passes reliably when run without sharding (or with a
different shard count) but produces intermittent failures when run with
Bazel's test sharding enabled at a specific shard count -- and the
specific failing test case(s) vary depending on shard count or run
order, pointing at cross-shard interference rather than a genuine test
bug.

## Likely causes

- **Test cases assigned to different shards (which run as separate,
  potentially concurrent test processes) share external mutable state**
  -- a shared database, a shared file, a shared external service --
  that individual test cases assumed would be exclusively theirs, an
  assumption that held when all tests ran serially in one process but
  breaks under sharded parallelism.
- **A test-sharding-aware test runner isn't correctly partitioning tests
  by the expected mechanism** (environment variables `TEST_SHARD_INDEX`/
  `TEST_TOTAL_SHARDS` not being read/respected by the test framework in
  use), causing an uneven or incorrect distribution that isn't obviously
  wrong but produces unexpected interactions.
- **Global/static state within the test binary itself** (a singleton, a
  module-level cache) isn't properly reset between test cases within a
  shard, and shard boundaries happen to change which tests run adjacent
  to each other, surfacing an existing test-isolation bug that shard
  count changes merely reveal rather than cause.
- **Resource contention between concurrently running shard processes**
  (port binding, temp directory naming) that assumed exclusivity works
  when only one test process runs at a time but fails when multiple
  shards run concurrently on the same machine.

## Diagnose

1. Reproduce with different shard counts (`--test_sharding_strategy`
   and explicit shard count flags) and note whether failures are
   consistent regardless of shard count (pointing at a general isolation
   bug) or specific to certain shard counts/combinations (pointing at
   specific interfering test pairs).
2. Check whether the test framework in use actually respects Bazel's
   sharding protocol (`TEST_SHARD_INDEX`, `TEST_TOTAL_SHARDS`
   environment variables) correctly, since not every test runner
   implements this correctly out of the box.
3. Identify any shared external resources (database, files, network
   ports) that test cases use, and check for exclusivity assumptions
   that don't hold under concurrent shard execution.
4. Check for global/static mutable state within the test binary that
   isn't reset between test cases, using the same diagnostic approach as
   general test-isolation debugging.

## Fix

Ensure each test case (or each shard) uses genuinely isolated resources
-- unique temp directories/ports/database instances per shard or per
test, rather than assuming exclusive access to a shared resource.
Confirm the test framework in use correctly implements Bazel's sharding
protocol; if it doesn't, either fix/configure it to do so or disable
sharding for that specific test target until it can be made shard-safe.
Fix any global/static mutable state to be properly scoped/reset per test
case, addressing the underlying isolation bug that sharding happened to
surface.

## Pitfalls

Don't disable test sharding as a permanent fix without understanding
whether the underlying isolation issue would also cause problems in
other parallel execution contexts (running the test suite on a
multi-core machine with generic test parallelism, for instance) -- the
sharding-specific symptom is often a symptom of a more general test-
isolation gap worth fixing properly rather than working around narrowly.

## Verify

Run the test target repeatedly with sharding enabled at multiple
different shard counts and confirm consistent, reliable results with no
further intermittent failures. Confirm resource isolation explicitly by
running shards concurrently and verifying (via logging or resource
naming) that no two shards ever contend for the same underlying
resource.
