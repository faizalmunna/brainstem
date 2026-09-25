---
name: module-level-init-runs-every-cold-start-unexpectedly
description: Global initialization code meant to run once actually re-executes on every cold start, causing repeated cost or unexpected side effects.
triggers: ["lambda global variable resets unexpectedly", "database connection recreated every invocation", "module level code running too often serverless", "cold start reinitializes state"]
permissions: ["READ"]
---

## Symptom
Code placed outside the handler function -- a database connection, a
loaded ML model, a cache client, a computed constant -- was written with
the assumption "this only runs once, when the container starts." In
practice, metrics show it running far more often than expected: connection
counts to a downstream DB climb roughly in proportion to invocation count
rather than staying flat, an expensive setup computation shows up
repeatedly in cold-start duration traces, or a piece of state that should
persist across invocations within the same container (a counter, an
in-memory cache) unexpectedly resets.

## Likely causes
1. **The execution environment is being recycled far more often than
   assumed** -- concurrency scaling means each concurrent invocation may
   land on a distinct fresh container, and the platform can also
   proactively recycle "warm" containers after a period of inactivity or
   after a certain number of invocations, so "once ever" is really "once
   per container lifetime," and container lifetimes can be much shorter
   than a developer's mental model of a long-lived server process.
2. **A deployment or configuration change (new function version,
   environment variable update, code update) forces all existing warm
   containers to be discarded**, so a burst of cold starts right after a
   deploy re-runs the "one-time" init code across every replacement
   container simultaneously, which can look like a sudden spike rather
   than steady-state behavior.
3. **The initialization code has a side effect that isn't idempotent**
   (incrementing an external counter, sending a startup notification,
   acquiring a lease) and was written assuming it fires once per
   deployment, when it actually fires once per cold start -- which under
   high concurrency during a traffic spike can mean dozens of "startup"
   events firing within seconds of each other.
4. **Provisioned concurrency or a keep-warm mechanism isn't configured (or
   isn't effective)**, so the function scales via ordinary on-demand cold
   starts far more frequently than the team assumed when they wrote the
   module-level code, especially for low-traffic functions where most
   invocations are cold.
5. **The init code itself is the source of intermittent failures under
   load** -- if it opens a new connection pool per cold start and cold
   starts spike during a traffic surge, the downstream service (a
   database with a fixed max-connections limit) sees a burst of new
   connection attempts that looks like a thundering herd, not steady
   traffic.

## Diagnose
- Compare the CloudWatch/platform "cold start" or "Init Duration" metric
  count against total invocation count over the same window -- a high
  cold-start ratio (not just an occasional one) confirms containers are
  being recycled far more often than "once ever."
- Add an explicit log line inside the module-level init code (not inside
  the handler) with a generated instance/container ID, and grep logs for
  how many distinct times that line fires per unit of traffic -- this
  directly falsifies the "runs once" assumption with hard evidence.
- Check the downstream dependency's own connection/session count metric
  (e.g., RDS `DatabaseConnections`) for a pattern that tracks invocation
  volume or concurrency rather than staying flat near a small, stable
  number -- that indicates connections are being recreated per cold
  start rather than reused.
- Review recent deployment history against the timestamps of any spike in
  cold starts -- a new version/config push invalidates existing warm
  containers, and the resulting synchronized cold-start burst is a known,
  expected (if under-appreciated) side effect of deploying.
- Check whether the function scales to high concurrency during traffic
  spikes (via the concurrent executions metric) -- each new concurrent
  container is a fresh cold start running the "once" code independently,
  so peak concurrency approximates a lower bound on how many times that
  code has run recently.

## Fix
Treat module-level/global initialization code as "runs once per container
lifetime, and container lifetimes are unpredictable and can be short,"
not "runs once ever" -- design it to be safe to re-run frequently and
concurrently. For expensive or side-effecting setup (external
notifications, counters, one-time migrations), move it out of the
function's init path entirely and into a genuinely one-time deployment
step (a migration script, a separate initialization Lambda invoked once)
rather than code that executes implicitly on every cold start. For
connection pooling, size the pool per container conservatively (e.g., 1-2
connections) since concurrency scaling multiplies containers, not
connections-per-container, and use provisioned concurrency or a proxy
(e.g., RDS Proxy) to bound the aggregate connection count independent of
how many containers exist. Make any global counter or cache explicitly
container-scoped in naming/logging so its resets are expected and
monitored, not mistaken for a bug.

## Pitfalls
Moving expensive setup into the handler "to be safe" (so it definitely
runs every invocation) trades an intermittent cost problem for a
guaranteed one, adding that cost to every single invocation's latency
instead of just cold starts -- the fix is making the module-level code
safe to re-run often, not eliminating module-level init altogether.
Another common mistake: assuming provisioned concurrency eliminates this
class of bug entirely -- it reduces cold-start frequency but doesn't make
it zero (provisioned instances can still be replaced during deploys or
scaling events), so init code still needs to tolerate re-execution.

## Verify
Force multiple cold starts deliberately (update an environment variable
to invalidate warm containers, or publish a new version) while watching
the container-ID log line from the init code and the downstream
dependency's connection-count metric -- confirm connection/resource
counts return to and stabilize at the expected steady-state level shortly
after the forced cold-start burst, rather than growing unbounded or
staying elevated.
