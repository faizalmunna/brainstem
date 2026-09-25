---
name: rds-connection-exhaustion-lambda-no-pooling
description: An RDS database rejects new connections with too-many-connections errors because concurrent Lambda invocations each open their own unpooled connection.
triggers: ["rds too many connections", "lambda database connection limit", "postgres remaining connection slots reserved", "rds proxy connection pooling", "lambda opening new db connection every invocation"]
permissions: ["READ"]
---

## Symptom
Under moderate traffic, the application starts seeing database errors
like `FATAL: too many connections for role` (Postgres),
`ER_CON_COUNT_ERROR` (MySQL), or generic connection-refused/timeout
errors from RDS, even though the database instance isn't CPU- or
memory-constrained -- it's specifically out of available connection
slots, and the pattern correlates with Lambda concurrency, not raw query
volume.

## Likely causes
1. **Each Lambda invocation opens a brand-new database connection with no
   pooling**, and because Lambda scales by running many concurrent
   execution environments, concurrent invocations translate directly and
   linearly into concurrent database connections -- 500 concurrent
   invocations means up to 500 simultaneous connections, quickly exceeding
   `max_connections` on all but the largest instance classes.
2. **Connections aren't being closed/released at the end of the handler**,
   so even at low concurrency, connections accumulate over time within a
   single execution environment or leak across warm invocations if a new
   connection is opened every time instead of reusing one already created
   at module scope.
3. **RDS Proxy is not in front of the database**, so there's no
   connection-multiplexing layer absorbing Lambda's connection-per-
   invocation pattern into a smaller, stable pool of actual backend
   connections.
4. **The instance's `max_connections` is set low relative to actual
   concurrency needs** (it scales with instance memory by default), so
   even a moderately pooled setup still exceeds it if the instance class
   is undersized for the workload's real concurrency.
5. **A connection pool exists in code but is sized incorrectly per
   execution environment** -- e.g., a pool with `max: 10` per Lambda
   instance, multiplied across dozens of concurrently warm execution
   environments, still adds up to far more connections than intended,
   because pooling within a single process doesn't cap the *aggregate*
   across many Lambda instances.

## Diagnose
- Check the RDS `DatabaseConnections` CloudWatch metric against the
  Lambda function's `ConcurrentExecutions` metric for the same window --
  a near 1:1 correlation strongly confirms connection-per-invocation
  behavior rather than a query-volume problem.
- Query `pg_stat_activity` (Postgres) or `SHOW PROCESSLIST` (MySQL)
  during a load spike to see the actual count and source of open
  connections, and check whether many connections are idle
  (`state = 'idle'`) rather than actively running queries -- idle-but-open
  connections are the signature of connections opened per-invocation and
  never reused.
- Review the Lambda handler code for where the database client/connection
  is instantiated -- if it's inside the handler function body (not at
  module/global scope, and not via RDS Proxy or a pooling library), that
  confirms cause 1/2 directly.
- Check whether an RDS Proxy is provisioned and whether the Lambda
  function's connection string actually points at the proxy endpoint
  versus the raw RDS endpoint -- it's a common half-fix to provision a
  proxy but leave the function's environment variable pointed at the
  database directly.
- Check `max_connections` on the instance (`SHOW VARIABLES LIKE
  'max_connections'` / the Postgres equivalent parameter) against the
  observed peak concurrent Lambda executions.

## Fix
Put RDS Proxy between Lambda and the database: Proxy maintains a warm,
pooled set of actual backend connections and multiplexes many
short-lived Lambda-side "connections" onto them, which is specifically
designed for exactly this Lambda-concurrency-vs-database-connection-limit
mismatch. Point the function's connection configuration at the proxy
endpoint, not the instance endpoint directly. Within the function code,
instantiate the database client/connection outside the handler (at module
load time) so a warm execution environment reuses its connection across
invocations instead of opening a new one every time, and ensure the
client library's own idle-timeout behavior matches Lambda's freeze/thaw
model (some drivers need explicit keep-alive or reconnect-on-error
handling because Lambda freezes the process between invocations). Size
`max_connections` and the proxy's own connection limits to real expected
peak concurrency with margin, and consider capping the Lambda function's
own reserved concurrency as a hard ceiling on how many simultaneous
invocations (and therefore proxy-side demand) can occur.

## Pitfalls
Adding RDS Proxy without also fixing per-invocation connection-opening in
code still helps (Proxy absorbs some of the churn) but doesn't eliminate
the underlying inefficiency -- the connection *setup* overhead per
invocation remains even if the backend connection count is now bounded.
Also, raising `max_connections` directly on the instance as a quick fix
just moves the ceiling higher without addressing the linear-scaling
problem, and each additional allowed connection consumes real memory on
the instance, which can degrade performance for legitimate queries under
sustained high concurrency.

## Verify
Under the same load pattern that originally caused connection errors,
confirm RDS `DatabaseConnections` stays roughly flat (near the pool/proxy
size) rather than scaling with `ConcurrentExecutions`, and confirm no
`too many connections` errors appear in application or database logs
during a sustained load test at expected peak concurrency.
