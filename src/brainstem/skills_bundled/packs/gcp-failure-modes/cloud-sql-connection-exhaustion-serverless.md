---
name: cloud-sql-connection-exhaustion-serverless
description: A Cloud SQL database runs out of available connections because a serverless compute platform scales out to many instances, each opening its own connection pool.
triggers: ["cloud sql too many connections", "cloud run database connection limit", "cloud function exhausts database connections", "cloud sql max connections exceeded"]
permissions: ["READ"]
---

## Symptom

A Cloud SQL instance starts rejecting new connections with a "too many
connections" error during periods of higher traffic, even though the
database's query load and CPU/memory usage don't look particularly high
-- the bottleneck is specifically the connection count, not query
throughput.

## Likely causes

- **A serverless compute platform (Cloud Run, Cloud Functions) scales out
  to many concurrent instances under load, and each instance maintains
  its own connection pool**, so total connections across all instances
  can exceed Cloud SQL's configured max connections even though each
  individual instance's pool size looks reasonable.
- **Each function/service instance's connection pool is sized for a
  single-instance mental model** (e.g. a pool of 10 connections, assumed
  to be "the" pool) without accounting for the multiplicative effect of
  many concurrent instances each holding their own separate pool of that
  size.
- **Connections aren't being reused efficiently within an instance's
  lifetime** -- opening a new connection per invocation instead of
  reusing a pooled connection across invocations handled by the same
  warm instance, unnecessarily inflating connection churn and count.
- **No connection pooler/proxy (like Cloud SQL Auth Proxy configured for
  pooling, or a dedicated proxy like PgBouncer) sits between the
  serverless layer and the database** to multiplex many logical
  application connections onto a smaller number of actual database
  connections.

## Diagnose

1. Check Cloud SQL's current connection count metric during the incident
   window and compare against the instance's configured max connections
   limit.
2. Check the compute platform's concurrent instance count during the same
   window (Cloud Run/Cloud Functions both expose this) and multiply by
   the configured per-instance pool size to estimate theoretical maximum
   connections -- if this exceeds the database's limit, the math itself
   confirms the issue.
3. Check application code for whether database connections are
   established once per warm instance (reused across invocations) or
   freshly created on every single invocation.
4. Check whether a connection pooler/proxy is in place between the
   application and the database, or whether each instance connects
   directly.

## Fix

Reduce per-instance connection pool size to account for the maximum
realistic number of concurrent instances, so total possible connections
stays under the database's limit with headroom. Reuse database
connections across invocations within a warm instance's lifetime rather
than opening a new connection per invocation. Introduce a connection
pooler (a managed option, or a self-hosted proxy like PgBouncer) between
the serverless layer and Cloud SQL to multiplex many application-level
connections onto fewer actual database connections, which is often the
most robust fix for genuinely bursty, highly concurrent serverless
workloads. Consider capping the compute platform's maximum instance
count if connection limits are the binding constraint and a pooler isn't
immediately feasible.

## Pitfalls

Don't simply raise Cloud SQL's max connections setting as the only fix
without addressing per-instance pool sizing -- a higher limit just moves
the ceiling further out without addressing the underlying multiplicative
scaling problem, and can also increase database memory overhead from
maintaining many connections. Also don't reduce per-instance pool size to
1 as an overcorrection, which can serialize concurrent requests within an
instance and hurt latency for legitimately concurrent workloads that
instance is meant to serve.

## Verify

Load-test to reproduce the original high-concurrency scenario and
confirm the database's connection count stays within its configured
limit throughout, with query latency remaining acceptable (confirming a
pooler, if added, isn't itself introducing unacceptable queueing delay).
