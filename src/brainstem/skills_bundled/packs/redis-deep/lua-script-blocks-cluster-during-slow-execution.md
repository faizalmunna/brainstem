---
name: lua-script-blocks-cluster-during-slow-execution
description: A Redis Lua script that runs longer than expected blocks all other clients from being served because scripts execute atomically on the single-threaded event loop.
triggers: ["redis lua script blocking", "eval command causing latency spike", "redis script atomic blocking other clients", "lua script too slow redis"]
permissions: ["READ"]
---

## Symptom

Redis latency spikes sharply and briefly for all clients at intervals
correlating with a specific Lua script (invoked via `EVAL`/`EVALSHA`)
being run, even though the script's logic looks simple -- the spike
duration scales with how much work the script actually does, not with
overall cluster load.

## Likely causes

- **The Lua script iterates over a large amount of data** (scanning many
  keys, processing a big collection) within a single script invocation,
  and because scripts run atomically and block the single-threaded event
  loop for their entire duration, every other client is queued behind it
  regardless of how simple each individual operation inside the script
  is.
- **The script was tested and tuned against a small dataset in
  development**, where its execution time was negligible, and nobody
  re-evaluated its performance characteristics as production data volume
  grew to a point where the same logic now takes meaningfully longer.
- **A script performs a data-dependent amount of work** (looping until a
  condition is met, processing a variable-length collection) whose worst-
  case execution time wasn't bounded or tested, so it usually runs
  quickly but occasionally takes much longer for a specific, larger-than-
  typical input.
- **Multiple scripts or the same script from multiple call sites compound
  in frequency**, so even if any single invocation is individually brief,
  frequent invocation means blocking time accumulates into a
  meaningfully worse aggregate latency profile than a single invocation's
  duration would suggest.

## Diagnose

1. Use Redis's slow log (`SLOWLOG GET`) to identify the specific script
   (by its SHA or content) responsible for the latency spikes and measure
   its actual execution time.
2. Correlate script execution time with the size of the data it operates
   over (the collection size, number of keys touched) to confirm whether
   execution time scales with a specific, identifiable input dimension.
3. Review the script's logic for any unbounded loop or data-dependent
   iteration whose worst case wasn't explicitly considered.
4. Check invocation frequency in production logs/metrics to determine
   whether occasional long individual runs or frequent moderate runs is
   the dominant contributor to overall impact.

## Fix

Rewrite the script to bound its work per invocation -- process data in
smaller batches across multiple script calls rather than one large
atomic operation, accepting a small loss of cross-call atomicity in
exchange for not blocking the event loop for an extended single window.
Where atomicity across the full operation genuinely matters, consider
whether the operation can be restructured using Redis's other primitives
(transactions with `MULTI`/`EXEC`, which don't block for external
computation the way a Lua script's internal loop can) or moved to
application-level logic with more granular Redis calls, if strict
single-script atomicity isn't actually required for correctness.

## Pitfalls

Don't assume a script is safe just because it was fast in testing --
explicitly test with production-representative data volume, and
re-evaluate whenever the relevant dataset's typical size changes
meaningfully. Also don't break up a script's atomicity carelessly if the
application genuinely depends on the entire operation being atomic --
verify what invariant the atomicity was protecting before splitting it
into multiple calls that could interleave with other clients' operations.

## Verify

Re-run the script against a production-scale dataset in a non-production
environment and measure its execution time to confirm it now stays
within an acceptable bound regardless of data size (either because it's
now batched, or because its logic was fixed). Monitor the slow log and
overall latency percentiles after deployment to confirm the periodic
spikes are gone.
