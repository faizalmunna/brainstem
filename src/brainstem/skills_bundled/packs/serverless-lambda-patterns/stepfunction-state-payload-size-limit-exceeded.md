---
name: stepfunction-state-payload-size-limit-exceeded
description: An orchestration workflow's state passed between steps exceeds the platform's payload size limit, causing an opaque execution failure.
triggers: ["step functions state size limit exceeded", "states.datalimitexceeded", "workflow execution fails payload too large", "orchestration step input too big"]
permissions: ["READ"]
---

## Symptom
A Step Functions state machine (or an equivalent orchestration/durable-
function workflow) fails partway through execution with an error like
`States.DataLimitExceeded`, and the failure doesn't point at any obvious
logic bug -- the same workflow definition has run successfully many times
before, and the specific execution that failed just happened to be
processing a larger input, a larger accumulated result, or more items in
a loop than usual.

## Likely causes
1. **The workflow passes full data payloads directly between states
   instead of references to the data**, so as a task's output (an entire
   API response body, a full row set from a query, a growing array
   accumulated across a Map/loop state) grows, the total state input/output
   size for a single state transition can exceed the platform's hard limit
   (for Step Functions, 256 KB per state transition), which most
   executions never approach until a larger-than-usual input arrives.
2. **A Map or iteration construct accumulates results from every iteration
   into a single combined output** rather than writing each iteration's
   result somewhere external and passing forward only a pointer/count, so
   the aggregate size scales with the number of items processed and
   eventually crosses the limit on inputs large enough, even though each
   individual iteration's payload was small.
3. **Upstream data growth is gradual and organic** -- the workflow was
   designed and tested against representative sample data early in the
   project, but real production data volume grew over time (more line
   items per order, more records per batch) until it silently crossed
   the threshold the original design never accounted for.
4. **Error payloads bloat the state under failure conditions** -- a task
   that fails passes its full error/cause payload (which can include a
   large stack trace or an echoed-back oversized input) into the next
   state's error-handling branch, so a state machine that behaves fine
   on the happy path fails specifically when handling certain errors
   because the error payload itself is what crosses the limit.
5. **A single task's output includes debug/diagnostic data that was never
   meant to flow through the state machine** (verbose logging fields, an
   entire upstream API response captured "just in case" rather than
   projecting out only the fields actually needed downstream), inflating
   payload size well beyond what the workflow logic actually consumes.

## Diagnose
- Read the specific failed execution's history in the console/API and
  identify exactly which state transition raised `States.DataLimitExceeded`
  -- this pinpoints which task's output (or which Map iteration's
  aggregate) is the oversized payload, rather than guessing across the
  whole workflow.
- Check the size of the actual input/output at that state for the failed
  execution versus a typical successful execution (log or capture the
  JSON size in bytes) to confirm this is a genuine size-limit issue tied
  to unusually large data, not an unrelated error being misattributed.
- Review whether the offending state involves a Map/iteration construct,
  and if so, check whether its `ResultPath`/output configuration
  aggregates every iteration's full output rather than a summary or count
  -- aggregate-output Map states are the most common source of
  size-limit failures that only manifest at higher item counts.
- Check whether the failure correlates with a recent increase in upstream
  data volume (more items in a batch, a larger customer's data) rather
  than any code or workflow definition change -- confirms organic data
  growth as the trigger, not a regression.
- Inspect the actual payload content for fields that are carried through
  but never read by any downstream state (dead data riding along in the
  JSON) -- these are safe, low-risk removal candidates that reduce size
  without changing behavior.

## Fix
Pass references, not full payloads, between states for any data that's
more than trivially small -- write large intermediate data to S3 (or the
platform's equivalent blob store) and pass forward the object key/URI,
having each subsequent state read what it needs directly from storage
rather than carrying it through the state machine's own JSON state. For
Map/iteration constructs, use the platform's result-aggregation options to
write each iteration's output to external storage and pass forward only a
manifest, count, or list of pointers, instead of concatenating every
iteration's full output into the Map state's own result. Trim task outputs
to only the fields actually consumed by later states (using `ResultSelector`/
output filtering where the platform supports it) rather than passing an
entire upstream response through unmodified. For error-handling branches
specifically, truncate or externalize large error payloads before they
flow into a Catch/Retry state so error handling doesn't inherit the same
size fragility as the happy path.

## Pitfalls
Reaching for "just pass everything through S3" indiscriminately for every
piece of state, including genuinely small values, adds unnecessary
latency (an extra read/write round trip per state) and operational
complexity (now every consumer needs S3 read permissions and error
handling for a missing/expired object) where a small JSON payload would
have been fine -- apply the S3-reference pattern specifically to the
payloads that are large or unbounded, not universally. Also, truncating
large payloads to fit under the limit without preserving a way to retrieve
the full data (e.g., silently dropping fields) can silently corrupt
downstream logic that assumed the full data was present, turning an
opaque size-limit failure into a much harder-to-detect correctness bug.

## Verify
Re-run the specific failed execution's input (or a synthetic input sized
to match or exceed it) through the updated workflow and confirm it
completes successfully; separately, instrument the state machine to log
actual payload size at each transition for a period after the fix and
confirm sizes stay well under the platform's limit even for the largest
realistic inputs, not just the one that originally failed.
