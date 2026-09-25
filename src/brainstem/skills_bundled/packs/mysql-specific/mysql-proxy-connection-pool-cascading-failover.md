---
name: mysql-proxy-connection-pool-cascading-failover
description: A ProxySQL or connection-pooling proxy layer exhausts its backend connections under load and triggers an unnecessary cluster-wide failover.
triggers: ["proxysql max connections error", "connection pool proxy triggered failover", "database failover happened for no reason", "proxysql backend marked shunned", "cluster failed over under load spike"]
permissions: ["READ"]
---

## Symptom
Under a traffic spike (or after a slow query pile-up), a MySQL proxy
layer (ProxySQL, MaxScale, or a similar pooling/routing proxy) starts
rejecting or queuing connections, marks backend nodes as unhealthy based
on connection saturation rather than actual node health, and triggers an
automated failover to a new primary -- even though the database nodes
themselves were healthy and the real bottleneck was the proxy's own
connection limits or health-check logic. The failover itself then causes
a availability blip or brief write unavailability that wouldn't have
been necessary if the underlying nodes had simply been left alone.

## Likely causes
1. **The proxy's max-connections limit (or per-backend connection pool
   size) is set lower than real peak application concurrency**, so a
   traffic spike exhausts the pool and the proxy starts queuing/rejecting
   new connections, which look identical to backend unavailability from
   the application's point of view.
2. **The proxy's health check conflates connection-pool saturation with
   backend-node health** -- a health check that fails when it can't
   acquire a connection from an already-exhausted pool (rather than
   directly probing the database node) reports the node as down when the
   node itself is fine, triggering failover logic built to react to
   "backend down" signals.
3. **A slow-query pile-up on one query pattern holds connections open
   long enough to starve the pool for everything else** -- a small number
   of slow or blocked queries (e.g., lock waits) can exhaust an
   undersized pool even though total query volume hasn't actually grown
   much, making the trigger look like "a spike" when it's really a small
   number of stuck connections.
4. **Failover automation has no minimum-confidence/quorum check before
   acting**, so a single proxy instance's transient view of backend
   health (possibly itself degraded, or affected by a network blip
   between just that proxy and the backend) is enough to initiate a
   cluster-wide failover, rather than requiring corroboration from
   multiple observers before treating a primary as actually down.
5. **The proxy and the database were sized independently**, with nobody
   revisiting the proxy's connection limits as the database's own
   `max_connections` or the application's instance count grew, so the
   proxy becomes the binding constraint without anyone intending it to be.

## Diagnose
- Check the proxy's own metrics/logs (ProxySQL: `stats_mysql_connection_pool`,
  `mysql_servers` status; MaxScale: its REST API/status output) for
  connection-pool saturation and backend `shunned`/`OFFLINE` status
  transitions timestamped against the incident window.
- Compare the proxy's configured max connections per backend against
  actual peak concurrent application connections during the spike --
  a pool consistently near its ceiling before the incident indicates
  sizing, not a genuine anomaly.
- On the database nodes directly (bypassing the proxy), check
  `SHOW PROCESSLIST` / `SHOW ENGINE INNODB STATUS` and general node
  health (CPU, I/O, replication status) for the same window -- if the
  nodes were healthy and responsive when queried directly, that confirms
  the proxy layer was the actual bottleneck, not the database.
- Identify whether a small number of specific queries were holding
  connections open unusually long (long-running or lock-waiting queries
  in `SHOW PROCESSLIST` with high `Time`) rather than a broad, even
  increase in query volume across the board.
- Review the failover automation's trigger logic for how many
  independent health signals it requires before acting, and whether a
  single proxy's view was sufficient to initiate the failover that
  occurred.

## Fix
- Size the proxy's connection pool and max-connections settings based on
  real peak application concurrency plus headroom, and revisit that
  sizing whenever the application's instance count or the database's own
  `max_connections` changes -- treat proxy connection limits as a
  capacity-planning input, not a fixed default left over from initial
  setup.
- Separate "can't get a pooled connection" from "backend node is down" in
  health-check logic -- a health check should probe the database node
  directly (a lightweight query on its own dedicated connection) rather
  than inferring node health from the shared application connection
  pool's saturation state.
- Add rate limiting or query timeouts for the specific query patterns
  prone to piling up and starving the pool, so a handful of slow queries
  can't single-handedly exhaust connection capacity meant for the whole
  workload.
- Require corroboration from multiple independent observers (multiple
  proxy instances, or a separate health-check path) before automated
  failover acts, so a single proxy's transient or localized view can't
  unilaterally trigger a cluster-wide failover.

## Pitfalls
- Simply raising the proxy's max-connections limit without checking
  whether the database's own `max_connections` and available memory can
  actually support that many concurrent connections just moves the
  saturation point from the proxy to the database itself.
- Disabling or loosening failover automation entirely as a reaction
  ("it fired incorrectly once, so turn it off") removes protection for
  the cases where failover genuinely is needed -- the fix is better
  signal quality and quorum, not no automation.
- Fixing only the connection-pool sizing without addressing the
  health-check design leaves the underlying "pool exhaustion looks like
  node death" conflation in place, ready to misfire the next time a
  different kind of spike hits the pool ceiling.

## Verify
Load-test the application against the proxy at a concurrency level that
previously triggered the false failover, and confirm via proxy metrics
that the connection pool stays within configured limits with headroom,
that health checks continue reporting backend nodes as healthy
throughout (verified against direct node health checks bypassing the
proxy), and that no failover event fires during the test.
