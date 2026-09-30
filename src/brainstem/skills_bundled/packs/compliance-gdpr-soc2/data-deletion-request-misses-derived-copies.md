---
name: data-deletion-request-misses-derived-copies
description: A user's GDPR data deletion request removes their record from the primary database but leaves copies of their data in backups, caches, logs, or downstream analytics systems.
triggers: ["gdpr deletion request incomplete", "right to erasure not fully implemented", "user data still in backups after deletion", "data deletion missed derived copy"]
permissions: ["READ"]
---

## Symptom

A user exercises their right to erasure (GDPR "right to be forgotten" or
an equivalent deletion request), and the application confirms deletion
by removing their record from the primary application database -- but
an audit or a follow-up complaint reveals their data still exists in
backups, a log aggregation system, a data warehouse, a cache, or a
third-party analytics tool that received a copy of it.

## Likely causes

- **The deletion process was implemented against only the primary
  database**, without an inventory of every other place personal data
  flows to (logs, caches, backups, data warehouse replication, analytics
  exports, third-party integrations), so deletion was structurally
  incomplete from the start.
- **Backups are treated as immutable/out-of-scope for deletion**, with no
  process to either purge specific records from backups or set a
  retention policy short enough that old backups containing the deleted
  data age out within an acceptable window.
- **Application logs routinely include personal data** (email addresses,
  names, IP addresses in request logs) with a retention period that
  outlives any specific user's deletion request, and log deletion was
  never considered part of the erasure process.
- **Data was replicated to a downstream system (analytics, a data
  warehouse, a marketing platform) at some point in the past**, and the
  deletion process has no mechanism to propagate deletion to those
  downstream copies, which continue holding the data indefinitely.

## Diagnose

1. Build (if it doesn't exist) a data flow inventory showing every system
   that receives or stores personal data, tracing from the primary
   application database outward through logs, caches, backups,
   analytics, and third-party integrations.
2. For a specific deletion request, check each system in that inventory
   for whether the deleted user's data is actually gone or still present.
3. Check backup retention policy and whether backups are ever
   specifically purged of individual records versus only expiring on a
   fixed schedule regardless of deletion requests.
4. Check logging configuration for what personal data fields are
   captured and how long logs are retained relative to typical deletion
   request handling time.

## Fix

Build (and keep current) a comprehensive data flow map covering every
system that stores or processes personal data, and design the deletion
process to propagate to every mapped system, not just the primary
database -- this may mean an explicit deletion API call to each
downstream system, or relying on a sufficiently short retention policy
for systems where per-record deletion isn't practical (logs, some backup
tiers), documented as the accepted approach for those specific systems.
Minimize personal data captured in logs in the first place (see this
domain's broader data-minimization practices) so there's less to worry
about propagating deletion to. For backups, either implement a
mechanism to purge specific records on restore/access, or ensure backup
retention is short enough that deleted data doesn't persist there
indefinitely, and document this retention period as part of the
erasure process's actual guarantee.

## Pitfalls

Don't claim "deletion complete" to the user or in compliance
documentation without actually verifying every mapped system, since an
incomplete deletion discovered later (by the user, or by a regulator) is
a worse outcome than being upfront about backup retention timelines from
the start. Also don't try to achieve instant, complete deletion from
literal immutable backup tape/archive systems if that's technically
infeasible -- document the realistic timeline (e.g. "fully purged from
backups within 90 days") rather than making an impossible promise.

## Verify

For a test deletion request, check every system in the data flow
inventory directly (not just the primary database) and confirm the
data is actually gone or on a documented, bounded path to being gone
(backup expiry). Periodically re-audit the data flow inventory itself
for new systems/integrations added since it was last updated, since a
map that goes stale reintroduces exactly this gap for newly added data
flows.
