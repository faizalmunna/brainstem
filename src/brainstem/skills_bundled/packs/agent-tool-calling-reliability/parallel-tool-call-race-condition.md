---
name: parallel-tool-call-race-condition
description: Multiple tool calls issued by the agent in the same turn run concurrently and produce wrong results due to an ordering dependency the framework doesn't enforce.
triggers: ["parallel tool calls conflict", "race condition in agent tool execution", "tool calls ran out of order", "concurrent tool calls corrupted state", "agent framework doesn't sequence dependent calls"]
permissions: ["READ"]
---

## Symptom
The model emits several tool calls in a single turn (many APIs support
this for latency) that the harness executes concurrently, and the result
is wrong or inconsistent in a way that depends on execution order or
timing -- e.g. a "create resource" and a "read resource" call issued
together where the read sometimes runs before the create commits, or two
calls that both write to the same file/record and the last-writer-wins
outcome isn't the one the model intended.

## Likely causes
1. **The agent framework parallelizes all tool calls in a turn by
   default** for latency, with no concept of a dependency between calls
   that happen to be requested together -- it doesn't know call B reads
   what call A writes.
2. **The model itself doesn't reason about execution order** when it
   emits multiple calls in one turn -- it's producing a list of intended
   actions, not a guarantee about scheduling, so it may issue a
   dependent pair assuming sequential semantics that the runtime doesn't
   provide.
3. **Tools with side effects on shared state have no locking/isolation**
   -- two concurrent calls both read-modify-write the same underlying
   resource (a counter, a file, a row) without a transaction or lock, so
   the outcome depends on interleaving.
4. **Idempotency/ordering assumptions differ between the tool
   implementation and the agent's mental model** -- a tool author assumed
   calls would always arrive sequentially (as in a synchronous script)
   and never tested concurrent invocation.

## Diagnose
- Check the agent framework's execution model for a single turn's tool
  calls -- confirm explicitly whether it runs them concurrently,
  sequentially, or concurrently-with-some-exceptions, since this is
  often undocumented default behavior rather than a deliberate choice.
- Reproduce with logging timestamps on each tool call's start/end and
  check whether the failure correlates with actual overlap (call B
  starting before call A finished) versus a purely logical ordering bug.
- Identify whether the calls in question share an underlying resource
  (same file, same DB row, same external account/session) -- races only
  matter where state is shared; independent calls to unrelated resources
  are safe to parallelize.
- Check whether the tool's own implementation is safe under concurrent
  invocation (does it use a transaction, a lock, an atomic operation) or
  whether it assumes single-caller access.

## Fix
Make ordering dependencies explicit and enforced by the harness, not
implicit in the model's intent. Two complementary approaches: (1) at the
harness level, group tool calls by declared side-effect scope (e.g. a
`resource_id` or `mutates` annotation on the tool schema) and only
parallelize calls that don't share scope, running calls that touch the
same resource sequentially in the order the model emitted them; (2) at
the tool implementation level, make shared-state operations atomic or
transactional (a DB transaction, a compare-and-swap, a per-resource lock)
so that even if calls do run concurrently, the result is one of the
valid serial orderings rather than a corrupted interleaving. Where a
genuine read-after-write dependency exists within one turn, prefer
exposing it to the model as a single composite tool (create-and-return)
rather than relying on either the model or the scheduler to get the
ordering right across two separate calls.

## Pitfalls
- Fixing this by forcing all tool calls to run strictly sequentially
  everywhere -- this eliminates the race but reintroduces the latency
  problem parallel execution was meant to solve; scope the fix to calls
  that actually share state, not the whole system.
- Adding a lock around a shared resource but not covering all code paths
  that touch it (e.g. a scheduled background job also writes the same
  row without acquiring the same lock) -- audit every writer, not just
  the tool-call path.
- Assuming the model will naturally avoid emitting conflicting parallel
  calls if the tool descriptions are just "clear enough" -- ordering
  guarantees belong in the execution layer, since the model has no
  reliable way to know or control how the harness schedules its calls.

## Verify
Construct a test turn where the model (or a scripted stand-in) emits two
calls with a known dependency (a write followed by a read of the same
resource) and run it through the harness repeatedly under load or
artificial delay injection -- confirm the read consistently reflects the
write's effect every time, not just in the common case, and that
unrelated concurrent calls still execute in parallel (confirming the fix
didn't regress to fully sequential execution).
