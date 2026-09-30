---
name: mongodb-secondary-overload-from-misrouted-reads
description: Diagnose a replica set incident made worse when troubleshooting an overloaded secondary accidentally routes its read traffic onto the primary.
triggers: ["secondary overloaded and now primary is slow too", "replica set incident got worse after we changed read preference", "failover made everything worse", "primary suddenly overloaded during replica set troubleshooting", "read preference change caused an outage"]
permissions: ["READ"]
---

## Symptom
One secondary in a replica set becomes overloaded (high CPU, replication
lag, or slow reads) under normal `secondaryPreferred` or `secondary`
read routing. During attempts to fix it -- removing the struggling
secondary from rotation, restarting it, or changing driver read
preference -- the *primary* also becomes overloaded and the incident gets
dramatically worse, sometimes triggering an election or full outage,
instead of getting better.

## Likely causes
1. **Read preference was changed or defaulted in a way that routes all
   reads to the primary** as a "quick fix" for the struggling secondary
   (e.g. switching from `secondaryPreferred` to `primary`, or a driver
   default nobody had audited), without accounting for the fact that the
   primary was never sized to carry both the full write load and the
   full read load simultaneously.
2. **Removing the unhealthy secondary from the replica set (or driver's
   pool) reduces the number of nodes read traffic can spread across**,
   so the same total read volume now concentrates on fewer remaining
   members, pushing at least one of them (frequently the primary, if
   `secondaryPreferred` falls back to it when no secondary is
   available) past its own capacity.
3. **No pre-established per-member capacity headroom** -- the replica
   set was sized assuming reads spread evenly across all secondaries
   at roughly steady-state load, with no plan for what happens to
   remaining capacity when one member is pulled out, so any single-node
   loss immediately overloads whatever absorbs its traffic.
4. **`secondaryPreferred` silently falling back to the primary** when no
   secondary is available/healthy is expected driver behavior, but if
   the team assumed the app was strictly `secondary`-only, they don't
   realize this fallback is what's driving load onto the primary until
   well into the incident.

## Diagnose
- Check the driver/application's configured read preference at the time
  of the incident (not just what was originally intended) --
  specifically, confirm what changed immediately before primary load
  increased, using deploy/config-change history correlated against the
  metrics timeline.
- On the primary, check `db.serverStatus().connections` and operation
  counters (`db.serverStatus().opcounters`) for a spike in read
  operations (`query`, `getmore`) coincident with the secondary being
  pulled from rotation or a read-preference change -- a primary that
  normally serves mostly writes suddenly serving significant read
  volume is the direct signature of misrouted traffic.
- Check replica set member health (`rs.status()`) for the timeline of
  when the struggling secondary was marked down/removed/restarted, and
  overlay that against the primary's load graph.
- Confirm what read preference mode was actually in effect
  (`secondaryPreferred` vs `secondary` vs `primary`) and whether a
  fallback to primary (which `secondaryPreferred` does automatically
  when no secondary is available) explains the traffic shift, as
  opposed to an explicit config change.

## Fix
- Before changing read routing during an incident, explicitly calculate
  whether the primary (or remaining secondaries) has headroom to absorb
  the redirected read volume on top of its existing load -- don't treat
  "route around the unhealthy node" as free.
- Prefer scaling out (adding a replacement secondary, or temporarily
  adding read capacity) over concentrating traffic onto fewer nodes when
  responding to a single overloaded member.
- If using `secondaryPreferred`, explicitly decide and document whether
  primary fallback is acceptable under degraded conditions -- if it
  isn't, use `secondary` mode with application-level handling for the
  case where no secondary is available (queue, degrade, or serve stale
  cached data) rather than silently loading the primary.
- Build in per-member capacity headroom at sizing time (e.g. size so the
  cluster tolerates losing one read replica without any remaining member
  exceeding a safe utilization threshold), and make that assumption
  explicit so a future incident responder knows the actual safety
  margin instead of guessing under pressure.

## Pitfalls
- Reflexively "failing over" to a new primary as a response to secondary
  trouble without first confirming the primary has capacity for the
  redirected load turns a partial, contained degradation into a
  full-cluster incident.
- Assuming `secondaryPreferred` never touches the primary -- its
  documented fallback behavior means any config or driver default using
  it can route to the primary the moment secondaries are unavailable,
  which is exactly the condition an incident creates.
- Fixing the immediate routing problem without addressing *why* the
  secondary became overloaded in the first place (e.g. an unindexed
  analytics query aimed at a secondary, see
  `mongodb-unindexed-query-backing-up-job-queue` for the general
  pattern) means the same node gets overloaded again once it's back in
  rotation.

## Verify
During a controlled test (e.g. simulated secondary removal in a staging
replica set under representative read load), confirm the primary's
operation counters and CPU stay within its documented safe headroom
after a secondary is removed from rotation, and that the configured read
preference behaves as documented (no unexpected primary fallback) under
that condition.
