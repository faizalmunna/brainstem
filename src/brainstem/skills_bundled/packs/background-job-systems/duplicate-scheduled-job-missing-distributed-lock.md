---
name: duplicate-scheduled-job-missing-distributed-lock
description: A periodic scheduled job runs twice for the same scheduled time because two separate scheduler or worker instances both triggered it independently.
triggers: ["cron job ran twice", "celery beat duplicated task", "scheduled job double execution", "periodic task fired by two instances", "cron running on every pod"]
permissions: ["READ"]
---

## Symptom
A periodic/scheduled job (an hourly report, a daily cleanup) executes twice for the same scheduled slot, and the duplicate is traced to two distinct scheduler or worker instances both independently firing the job -- not to the broker's own redelivery/ack mechanics.

## Likely causes
1. **The scheduler component itself runs as more than one replica** for availability (multiple Celery beat instances, multiple app processes each running an in-process scheduler like APScheduler or `node-cron`) with no coordination between them, so every replica independently fires the same scheduled task at the same wall-clock time.
2. **A rolling deploy briefly overlaps old and new scheduler instances**, so both are alive and scheduling simultaneously during the transition window, even though only one instance is intended at steady state.
3. **A "prevent duplicate" check exists but isn't atomic** -- e.g. reading a `last_run` timestamp and then updating it as two separate steps -- so two instances can both read "not yet run" before either writes back, and both proceed.
4. **A distributed lock exists but its TTL is shorter than the job's actual runtime**, so a second instance acquires the lock partway through the first's legitimate execution, having assumed the first instance died.

## Diagnose
- Check the scheduler's actual current deployment topology (not just the intended replica count) -- an old instance still alive right after a deploy is a common surprise.
- Grep logs for the scheduled job's identifying log line across every instance/host around the same scheduled timestamp, to confirm two distinct processes executed it rather than one process logging twice.
- If a lock mechanism already exists, check whether it's a single atomic operation (`SET NX`, a conditional update with a unique constraint) versus a separate read-then-write, and check its TTL against the job's p99 runtime.

## Fix
Use a single atomic distributed lock, acquired immediately before execution as one atomic operation (Redis `SET key value NX PX <ttl>`, a database row with a unique constraint plus a conditional update, or the framework's own leader-election primitive) -- never a separate check-then-set. Set the lock's TTL comfortably above the job's expected runtime, with the holder renewing it (a heartbeat/lease extension) while still executing, so it can't expire mid-run and be reacquired by a second instance. Prefer designating a single leader for scheduling over "every instance attempts everything and locks resolve collisions" -- reduces how often the lock is even contended, and makes overlap during deploys the exception rather than the routine case. For rolling deploys specifically, ensure the old scheduler instance is fully drained before considering the transition complete, rather than just confirming the new one is up.

## Pitfalls
A lock with no TTL is worse than one that's slightly too short -- if the holder crashes without releasing it, the job never runs again until someone intervenes manually; always pair a TTL with renewal, never an unbounded lock. Locking at too coarse a granularity (one global lock covering every scheduled job) serializes unrelated jobs against each other unnecessarily -- scope the lock key to the specific job/task identity.

## Verify
Run two scheduler instances simultaneously against the same lock backend in a test environment (deliberately, to reproduce the failure condition) and confirm only one actually executes the job's body for a given scheduled run, while the other logs a clean "lock held, skipping" outcome.
