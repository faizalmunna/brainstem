---
name: synchronous-function-chaining-cascading-timeouts
description: A function that synchronously invokes another function creates a nested chain prone to cascading timeouts, retry storms, and hidden cost.
triggers: ["lambda calling lambda synchronously", "nested function invocation timeout", "function chain retry storm", "lambda invoking lambda directly slow"]
permissions: ["READ"]
---

## Symptom
Function A calls function B directly (an SDK `invoke` call, or an HTTP
call to another function's URL/API Gateway endpoint) and waits for the
response before continuing. Under normal load this works, but during a
slowdown or partial outage, A's invocations start timing out or piling up
because they're blocked waiting on B, B's own concurrency gets consumed
by A's calls, and if either layer retries on failure, the same logical
request multiplies into several concurrent executions across both
functions -- consuming concurrency and cost far out of proportion to the
actual traffic, and making the root cause hard to find because the
failure surfaces as "A is slow" when the real problem is deep in B or a
dependency of B.

## Likely causes
1. **A's timeout is not set meaningfully shorter than B's timeout**, so
   when B is slow, A doesn't fail fast -- it waits nearly as long as B's
   full timeout budget, holding its own execution slot (and any resources
   it acquired) the entire time, which multiplies the effective latency
   and concurrency consumption of a single slow request across two
   functions instead of one.
2. **Both layers retry on failure independently and neither is aware of
   the other's retry behavior**, so a single client-facing failure can
   become several actual invocations of B (A's retries) each potentially
   also retried by whatever triggered A, turning a transient blip into a
   multiplicative retry storm that looks like a traffic spike.
3. **A's own concurrency limit isn't sized with B's capacity in mind**, so
   a burst of traffic to A generates a proportional burst of concurrent
   synchronous calls to B, and if B has a lower reserved concurrency limit
   (or shares the account pool with other functions), B starts throttling
   -- which then causes A's calls to fail or hang, even though A itself
   never exceeded its own concurrency limit.
4. **The synchronous chain exists for convenience rather than necessity**
   -- A needs some result from B to proceed, but the actual latency/cost
   requirements would tolerate an asynchronous handoff (a queue, an event)
   instead, and the synchronous call was the easiest thing to write, not
   the most resilient thing to run.
5. **Cost is invisible until the bill arrives** because each of A's
   invocations now bills for the wall-clock time spent blocked waiting on
   B, so A's cost scales with B's latency even though A's own code does
   almost no work during that wait -- a slow B silently makes A
   expensive too.

## Diagnose
- Trace a single request end-to-end (X-Ray or equivalent distributed
  tracing) through both A and B and look at how much of A's total duration
  is spent inside the call to B versus A's own logic -- a large fraction
  spent waiting confirms the chain is the latency driver, not A's code.
- Compare A's and B's configured timeouts directly -- if A's timeout is
  equal to or greater than B's, A cannot fail fast when B is genuinely
  stuck, and will instead hold its slot for close to B's full timeout.
- Check both functions' `Throttles` and `ConcurrentExecutions` metrics for
  the same incident window -- if B throttles while A's own invocation
  count looks unremarkable, the chain is transmitting B's capacity problem
  upstream to A's callers.
- Look for retry configuration at every layer in the chain (the original
  trigger, A's own retry-on-invoke logic, B's event source retry policy)
  and multiply them out -- a retry count of 3 at each of two layers can
  turn one logical request into up to 9 actual invocations of the deepest
  function under sustained failure.
- Check billed duration and invocation count for A specifically during
  periods when B was known to be slow -- a visible cost/duration spike in
  A correlated with B's slowness (rather than with A's own traffic volume)
  confirms the hidden cost-coupling.

## Fix
Prefer asynchronous decoupling (a queue, an event bus, a step-function-style
orchestration with a callback) over a direct synchronous invocation
whenever A doesn't need B's result to respond to its own caller
immediately -- this removes the blocking wait entirely and lets each
function scale and fail independently. Where a synchronous call is
genuinely required, set A's timeout meaningfully shorter than B's (and
budget for network/cold-start overhead on top), and set the downstream
client's own connect/read timeout even shorter still, so A fails fast and
predictably instead of hanging near B's full timeout. Coordinate retry
policy across the chain deliberately -- if B's event source or client
already retries, A generally should not add its own retry on top without
reducing or disabling one of the layers, and any retry should use
exponential backoff with a cap on total attempts across the whole chain.
Size A's concurrency (reserved concurrency) with B's actual capacity in
mind, not just A's own expected traffic, so a burst to A can't
mechanically exceed what B can sustain.

## Pitfalls
Replacing a synchronous call with an async queue but then having A poll
the queue/result store in a tight loop waiting for B's answer just moves
the blocking wait into a different shape without removing it, and can
burn more invocation time (and cost) than the original direct call.
Also, adding retries "for resilience" without also adding idempotency to
whatever B does is a common way to turn a chain's transient failure into
duplicated side effects (double-charging, double-sending) rather than
just duplicated work.

## Verify
Introduce artificial latency or a forced failure into B in a test
environment and confirm A fails fast at its own reduced timeout (not at
B's full timeout), that the total number of actual invocations of B for
one logical request stays within the intended retry budget (check
invocation counts, not just the final outcome), and that A's concurrency
and billed duration during the test don't scale linearly with B's induced
slowness.
