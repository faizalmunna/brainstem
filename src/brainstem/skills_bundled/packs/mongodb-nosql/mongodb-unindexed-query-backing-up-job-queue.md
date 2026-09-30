---
name: mongodb-unindexed-query-backing-up-job-queue
description: Diagnose a build or job queue system silently backing up because an unindexed MongoDB query slows down under growing collection size.
triggers: ["job queue backing up for no obvious reason", "jobs pending for a long time before starting", "queue depth growing slowly over days", "worker polling query getting slower over time", "everything was fine until the collection got bigger"]
permissions: ["READ"]
---

## Symptom
A queue-backed system (build jobs, background tasks, scheduled work)
develops a growing backlog over hours or days rather than failing
loudly -- jobs are submitted and eventually processed, but the time
between submission and pickup keeps increasing, and standard uptime/
error-rate monitoring shows nothing wrong because no request is actually
erroring, just running late. By the time anyone notices via user
complaints, the backlog is large and painful to drain.

## Likely causes
1. **The worker's "find next job to run" query has no supporting index**
   and the jobs collection has grown past the point where a collection
   scan is cheap -- each poll gets linearly more expensive as the
   collection (including completed/historical jobs, if they aren't
   pruned or moved out) grows.
2. **An index exists but doesn't match the actual query shape** -- e.g.
   the query filters on `status` and sorts by `createdAt`, but the index
   only covers `status`, so MongoDB still scans and sorts all matching
   documents in memory instead of using an index to satisfy both the
   filter and the sort.
3. **No alerting exists on query latency or queue age specifically** --
   only on request error rate or overall uptime, both of which stay
   green while jobs merely take progressively longer, so the regression
   is invisible until the backlog is severe enough to generate user
   complaints.
4. **Completed/historical job documents are never archived or deleted**,
   so the collection the polling query scans grows unbounded even though
   only a small "pending" subset is ever actually relevant to the
   worker's query.

## Diagnose
- Run the worker's actual polling query with `.explain("executionStats")`
  against a production-sized collection and check `totalDocsExamined`
  vs. `nReturned` -- a large ratio confirms the query is scanning far
  more documents than it returns.
- Check `executionStats.executionTimeMillis` trend over time (or via
  `db.currentOp()` sampled repeatedly during a normal period) to see if
  this specific query is the one getting slower, as opposed to a
  system-wide resource issue.
- Check `db.collection.getIndexes()` against the actual filter+sort
  fields the polling query uses, and confirm whether an index exists
  that covers the query's filter predicate *and* its sort field.
- Check collection growth over time (`db.collection.stats().count`
  sampled periodically, or growth in `db.collection.totalSize()`) --
  a query that was fast at 10K documents can be unacceptably slow at
  10M if it was never indexed, and the growth curve maps directly onto
  when the slowdown likely started.
- Confirm whether queue-age or job-pickup-latency is actually being
  measured and alerted on separately from HTTP error rate/uptime --
  absence of this metric is itself a root cause, not just a diagnostic
  gap.

## Fix
- Add a compound index matching the polling query's actual shape: filter
  fields first (e.g. `status`), then the sort field (e.g. `createdAt`),
  so MongoDB can use the index to satisfy both the filter and the sort
  without an in-memory sort stage.
- Separate "active/pending" jobs from historical/completed ones --
  either via a partial index (`{ status: 1, createdAt: 1 }` with a
  partial filter expression on pending states) so the index only covers
  rows the worker actually queries, or by moving completed jobs to a
  separate collection/archive on a schedule.
- Add explicit alerting on queue age / oldest-pending-job-age and on
  the polling query's own latency, not just on request error rate --
  this is a leading indicator that catches the regression while the
  backlog is still small and cheap to drain.
- If the collection is large and growing, consider a TTL index on
  completed jobs (auto-expiring documents past a retention window) so
  the scanned collection size stays bounded regardless of historical
  volume.

## Pitfalls
- Adding an index on `status` alone "fixes" the `explain()` output's
  scan count for the filter but still leaves an in-memory sort on
  `createdAt` for every poll if the sort field isn't part of the same
  compound index -- verify the plan shows no `SORT` stage, not just an
  `IXSCAN`.
- Fixing the query without adding the age/latency alert means the same
  failure mode recurs silently the next time the collection grows past
  a threshold, since nothing will surface the next regression before
  it's user-visible again.
- Archiving old jobs into a separate collection but leaving the worker's
  query unchanged (still scanning the original, now let's-say-pruned
  collection) only delays the problem until the "active" collection
  itself grows past the same threshold -- the index fix and the
  archiving fix are complementary, not substitutes for each other.

## Verify
Re-run `.explain("executionStats")` on the polling query and confirm
`totalDocsExamined` is close to `nReturned` with no `SORT` stage in the
winning plan, then confirm via the new queue-age metric that job pickup
latency stays flat (not climbing) as the collection continues to grow
under normal production write volume.
