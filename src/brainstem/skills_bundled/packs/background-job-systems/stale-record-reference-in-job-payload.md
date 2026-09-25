---
name: stale-record-reference-in-job-payload
description: A queued job fails or misbehaves at execution time because its payload references a database record that was deleted or changed after the job was enqueued.
triggers: ["job crashes on deleted record", "background task references stale data", "foreign key not found in worker", "job payload out of date", "task fails because row no longer exists"]
permissions: ["READ"]
---

## Symptom
A job fails with a "not found"/null-reference error when it finally runs, or worse, silently operates on incorrect data -- tracing back to the job's payload holding an ID (or a full snapshot) for a database record that was deleted, or changed, in the window between when the job was enqueued and when it actually executed.

## Likely causes
1. **The payload was serialized as a full object/field snapshot at enqueue time** instead of just an identifier, so by execution time the embedded data is stale even before considering whether the record still exists at all.
2. **The payload correctly holds just an ID, but the referenced row was deleted** in the interim (a user deleted their account, an admin cleanup ran, a cascading delete fired), and the job's lookup code doesn't treat "not found" as a distinct, expected outcome from an actual bug.
3. **Queue backlog widened the enqueue-to-execution window** far beyond what was assumed when the job was designed, turning a theoretically-rare race into a routinely-occurring one once the queue is running behind (see the worker-concurrency backlog pattern).
4. **No coordination between the deletion path and the job queue** -- deleting a record doesn't cancel or remove jobs already enqueued that reference it, so an orphaned job is guaranteed to eventually run against a record that's gone.

## Diagnose
- Inspect the actual serialized job payload (log it, or read the raw broker message body) to confirm whether it carries an ID or a stale snapshot of full field values.
- Check the job handler's lookup code for how a missing record is handled: does a `None`/`nil` result raise an exception that retries forever against a record that will never come back, or is it handled as an expected, distinct "skip" outcome?
- Compare the record's deletion timestamp (an audit log, or a soft-delete `deleted_at`) against the job's actual execution timestamp, and compare that gap against typical queue latency, to confirm the race is realistic given actual backlog sizes rather than purely theoretical.

## Fix
Serialize only stable identifiers into the job payload, never full object state, and always re-fetch current data from the source of truth at execution time -- the payload says *which* record to act on, not what was true about it earlier. Handle "referenced record no longer exists" as a normal, expected terminal outcome: log it at low severity, mark the job as skipped, and do not retry, since retrying cannot un-delete the record. Where the domain allows it, prefer soft deletes (a `deleted_at`/tombstone flag) for records that background jobs may reference, so a job can distinguish "flagged deleted, skip gracefully" from a genuinely corrupted or unexpected missing reference worth investigating. For jobs whose correctness depends on the record still being *valid*, not merely *present*, at execution time, add an explicit freshness check (an `updated_at`/version comparison) rather than assuming existence implies the data is still accurate.

## Pitfalls
Silently ignoring every "not found" case with no logging removes visibility into how often it actually happens -- log it, even at low severity, so a spike after a bulk-delete operation is distinguishable from a new bug. Re-fetching at the start of execution fixes enqueue-to-execution staleness but not staleness *within* a long-running job if the record changes again mid-execution -- for jobs sensitive to that, use optimistic locking (a version check on write) rather than assuming the record is frozen for the job's entire duration.

## Verify
Enqueue a job referencing a record, delete that record before the job executes (simulating realistic queue delay), and confirm the job completes as a clean, logged no-op/skip rather than raising an unhandled exception or retrying indefinitely.
