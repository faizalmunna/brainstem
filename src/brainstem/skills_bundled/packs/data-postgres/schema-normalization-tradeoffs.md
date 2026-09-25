---
name: schema-normalization-tradeoffs
description: Decide how much to normalize a relational schema, and diagnose bugs/performance problems caused by either under-normalization (duplicated, driftable data) or over-normalization (excessive joins for simple reads).
triggers: ["normalize database schema", "denormalize for performance", "duplicated data database", "too many joins slow", "schema design database"]
permissions: ["READ", "DATABASE"]
---

## Symptom
Either: the same logical fact is stored in multiple places and drifts out
of sync (a user's display name stored redundantly on every one of their
posts, updated in one place but not the others), or a simple, frequent
read requires joining many tables together, adding latency and complexity
disproportionate to how simple the data conceptually is.

## Likely causes
1. **Under-normalization**: a value copied into multiple tables "to avoid
   a join" without a mechanism to keep the copies in sync, so an update
   to the source of truth doesn't propagate, and different parts of the
   system show inconsistent values for what should be the same fact.
2. **Over-normalization**: data split into many small tables strictly
   following normal-form rules even where a frequently-read, rarely-
   changed aggregate would be simpler and faster as a single denormalized
   row or column, at some deliberate, documented cost to update
   complexity.
3. **No clear single source of truth** for a piece of data that
   conceptually should have exactly one -- multiple tables each holding a
   version of it, with no clear rule for which one is authoritative
   when they disagree.
4. **A performance-driven denormalization introduced without a
   consistency mechanism** (a cached count, a materialized aggregate)
   that silently drifts from the real underlying data over time as edge
   cases (failed updates, direct database edits, migrations) aren't
   accounted for.

## Diagnose
- For a specific case, identify: is this data duplicated because two
  tables genuinely need independent copies for correctness (rare), or was
  it duplicated purely to avoid a join (the common under-normalization
  case)?
- Check whether existing denormalized/duplicated fields have a
  synchronization mechanism (a trigger, an application-level update-both-
  places pattern, a scheduled reconciliation job) or if they're simply
  written once and drift silently.
- For over-normalization complaints, measure whether the join in question
  is actually a measured performance problem (via `EXPLAIN ANALYZE`) or
  just a perceived complexity annoyance -- these call for different
  responses.

## Fix
- For under-normalization causing drift, either remove the duplicate and
  join to the source of truth at read time (if the join's actual cost is
  acceptable), or, if the duplication is kept deliberately for
  performance, add an explicit synchronization mechanism (a database
  trigger, or an application-layer transaction that updates both the
  source and the denormalized copy atomically) so drift becomes
  structurally impossible rather than just unlikely.
- For a measured, real performance problem from excessive joins on a hot
  read path, denormalize deliberately: store a computed/aggregated value
  (a cached count, a flattened frequently-joined field) alongside clear
  documentation of what keeps it in sync and how it should be recomputed
  if it ever drifts (a reconciliation job as a safety net).
- Establish and document one clear source of truth per logical fact, even
  when denormalized copies exist elsewhere for performance -- the
  documentation itself prevents future confusion about which value to
  trust when they disagree.
- Prefer normalized design by default for anything without a measured
  performance need to denormalize -- treat denormalization as a
  deliberate trade-off made for a specific, verified reason, not a
  default optimization applied preemptively.

## Pitfalls
- Denormalizing "for performance" without ever measuring whether the
  normalized version was actually too slow adds real maintenance burden
  (sync logic, drift risk) for a benefit that may not have existed.
- A reconciliation job that fixes drifted denormalized data without
  alerting when it finds and corrects a mismatch hides how often the
  primary sync mechanism is actually failing -- log/alert on
  reconciliation corrections, don't just silently fix and move on.
- Removing duplication by adding a join to a hot, high-traffic query path
  without checking the join's actual cost first (index support, row
  counts involved) can turn a fast-but-inconsistent query into a slow-
  but-consistent one -- verify the join performs acceptably before
  committing to the normalized version as the fix.

## Verify
For a drift fix, update the source-of-truth value and confirm (via a
query, not just inspection) that every denormalized copy reflects the new
value within the expected synchronization window; for a performance-
driven denormalization, confirm via `EXPLAIN ANALYZE` that the new,
flatter read path is measurably faster than the joined version it
replaced.
