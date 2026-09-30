---
name: function-durable-orchestrator-replay-side-effect-bug
description: A Durable Functions orchestrator produces duplicate side effects or wrong results because non-deterministic code runs again during replay.
triggers: ["durable function orchestrator running twice", "durable functions duplicate emails or calls", "orchestrator function non-deterministic error", "durable function replay causing duplicate side effects"]
permissions: ["READ"]
---

## Symptom
A Durable Functions orchestrator appears to send duplicate notifications,
make duplicate downstream API calls, or produce inconsistent results
across runs of what should be the same deterministic workflow -- and the
Function host logs show the orchestrator function's code executing
multiple times for what the orchestration history considers a single
logical run, without any explicit retry being configured.

## Likely causes
1. **The orchestrator function contains non-deterministic code directly**
   (calling `DateTime.Now`/`Guid.NewGuid()`, reading environment variables
   that can change, making a direct HTTP call, or using `Task.Delay`
   instead of `context.CreateTimer`) -- the Durable Functions runtime
   replays the orchestrator function from the top on every new event
   (activity completion, timer fire, external event) to reconstruct its
   current state from history, and any code that produces a different
   result on replay than it did originally desyncs the orchestration from
   its own history, which can manifest as skipped or duplicated logic.
2. **A side-effecting operation (sending an email, calling a payment API)
   was placed directly in orchestrator code instead of inside an Activity
   Function**, so every replay re-executes that side effect for real,
   since the orchestrator's job is to *schedule* activities
   deterministically, not to perform I/O itself -- the framework only
   memoizes Activity Function *results*, not arbitrary code the
   orchestrator happens to run inline.
3. **An Activity Function itself isn't idempotent, and the orchestration
   host restarted or scaled mid-execution**, causing the Durable Task
   framework's own at-least-once activity execution guarantee to invoke
   the same activity a second time after a host failure, which is expected
   framework behavior but breaks visibly if the activity's side effect
   (e.g., "charge the customer") wasn't designed to tolerate being run
   twice for the same logical operation.
4. **The orchestrator's code changed (a new deployment) while instances
   from the previous version were still mid-flight**, so replaying old
   history against new orchestrator code takes a different logical path
   than the history recorded, producing a
   `NonDeterministicOrchestrationException` or, worse, silently wrong
   behavior if the code change wasn't structural enough to trigger the
   framework's own detection.
5. **`context.CurrentUtcDateTime` or `context.NewGuid()` (the
   orchestration-safe equivalents) were available but not used**, with
   ordinary language APIs used instead in a codebase that mixed both
   patterns across different orchestrators, so only some orchestrators
   exhibit the bug depending on which one a given engineer wrote most
   recently.

## Diagnose
- Search orchestrator function code specifically (not Activity Function
  code, where these APIs are fine) for direct calls to `DateTime.Now`/
  `DateTime.UtcNow`, `Guid.NewGuid()`, `Task.Delay`, `Random`, or any
  direct `HttpClient`/SDK call -- any of these inside an orchestrator
  function body is a concrete, greppable signal independent of observed
  symptoms.
- Check Application Insights or Durable Functions' built-in
  `durable-functions-history` table/`GetStatusAsync` history for the
  specific orchestration instance and count how many times a given
  activity or action appears scheduled versus how many times it should
  logically have run once -- a mismatch confirms replay-induced
  duplication rather than an intentional retry policy.
- Check the Function App's deployment history/timestamps against the
  orchestration instance's start time -- if a new deployment landed while
  the instance was still running, code-change-during-replay is a plausible
  contributing cause, and the host logs may show
  `NonDeterministicWorkflowException` directly.
- Review whether Activity Functions called from the orchestrator are
  themselves idempotent (safe to execute twice with the same input) --
  if not, and the host has had any recent restarts/scale events (check
  Function App restart history), duplicate activity execution from the
  framework's at-least-once guarantee is a distinct, valid explanation
  from orchestrator non-determinism.
- Enable Durable Functions' verbose/diagnostic logging
  (`durableTask.tracing` settings in `host.json`) temporarily to see
  explicit replay markers and confirm which code paths actually re-execute
  on replay versus which are correctly skipped via history replay.

## Fix
Keep orchestrator functions strictly deterministic: move every side
effect (HTTP calls, sending messages, database writes, anything with an
observable external effect) into an Activity Function called via
`context.CallActivityAsync`, and use only the orchestration context's
deterministic equivalents (`context.CurrentUtcDateTime`,
`context.NewGuid()`, `context.CreateTimer` instead of `Task.Delay`) for
anything that would otherwise be non-deterministic. Design every Activity
Function to be idempotent with respect to its own logical operation (e.g.,
using an idempotency key when calling a payment API) so the framework's
at-least-once execution guarantee after a host restart is safe rather than
dangerous. Version orchestrator code changes carefully -- prefer adding
new orchestrator versions/functions for structural changes and letting
in-flight instances of the old version drain, rather than editing a live
orchestrator's logic in place while instances are running against its
history.

## Pitfalls
Wrapping a non-deterministic call in a try/catch to suppress the
`NonDeterministicWorkflowException` without addressing the actual
non-determinism hides the symptom while leaving the underlying desync
(and its duplicate side effects) fully intact. Also, making an Activity
Function idempotent by adding a naive "check if already done" read before
write introduces its own race condition if two replays or retries can
race each other -- idempotency needs an atomic mechanism (a conditional
write keyed on an idempotency token, e.g., a Cosmos DB conditional insert)
rather than a check-then-act pattern.

## Verify
Force a replay deliberately (e.g., raise an external event or let a timer
fire on a test orchestration instance) and confirm via Application
Insights/history inspection that no Activity Function re-executes more
times than intended, and that no direct side effect (visible in a test
mailbox, a mock payment endpoint's call count) duplicates. Simulate a host
restart mid-orchestration (recycle the Function App during a running test
instance) and confirm the orchestration resumes correctly with each
Activity Function's idempotency guarding against any duplicate execution
the framework itself performs.
