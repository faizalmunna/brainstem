---
name: blue-green-cutover-before-target-warm
description: A blue-green deployment's traffic cutover causes a latency or error spike because the new environment's caches and connection pools were still cold.
triggers: ["latency spike right after blue green cutover", "cold cache after switching traffic", "connection pool exhausted after deploy switch", "new environment slow right after cutover", "blue green swap caused a spike"]
permissions: ["READ"]
---

## Symptom
Immediately after a blue-green deployment flips traffic (load balancer,
DNS, or router switch) from the old environment to the new one, users
see a sharp but temporary spike in latency, timeouts, or error rate that
settles down on its own within a minute or two -- the new environment was
technically "up" and passing basic health checks, but not actually ready
to serve production-level load the instant it received it.

## Likely causes
1. **Connection pools start empty** -- database connection pools, HTTP
   keep-alive pools to downstream services, and thread/worker pools are
   sized and warmed under load, not at idle; the instant full production
   traffic arrives, every request pays the cost of establishing a new
   connection (TCP handshake, TLS negotiation, auth) until the pool fills.
2. **In-process or local caches are cold** -- caches that were populated
   in the old (blue) environment over hours/days of traffic (in-memory
   LRU caches, JIT-compiled hot paths, ORM query-plan caches) don't exist
   in the freshly-started new (green) environment, so the first wave of
   requests all take the slow, uncached path simultaneously.
3. **The health check that gated cutover only checks liveness, not
   warmth** -- it passed as soon as the process could respond to a
   trivial ping, which says nothing about whether its pools/caches have
   reached steady state, so "health check green" and "actually ready for
   full load" are treated as the same thing when they aren't.
4. **Cutover is instantaneous (all-or-nothing) rather than gradual** --
   100% of traffic moves in one switch instead of being ramped, so there
   is no low-volume period during which the new environment can warm up
   under real (but partial) load before bearing the full weight.
5. **Autoscaling in the new environment hasn't caught up** -- the green
   environment was provisioned at a baseline instance count, and
   traffic-based autoscaling triggers reactively after the spike already
   started, not proactively before cutover.

## Diagnose
- Correlate the latency/error spike's timestamp precisely against the
  load balancer's/router's traffic-switch event -- confirm the spike
  starts at cutover, not slightly before or after (which would point at
  a different cause).
- Check connection pool metrics (active/idle connections, pool
  saturation, connection-establishment time) for the new environment in
  the first minutes after cutover versus its steady-state values.
- Check cache hit-rate metrics for the new environment immediately
  post-cutover -- a hit rate near zero that climbs over the following
  minutes directly confirms cold-cache as a contributing cause.
- Review exactly what the pre-cutover health/readiness check verified --
  does it check pool fill level or cache population at all, or only
  process liveness?
- Check whether the cutover mechanism supports (and was configured for)
  gradual traffic ramping, or whether it is a hard instantaneous switch.

## Fix
Add an explicit warm-up phase between "new environment is deployed and
passing liveness checks" and "new environment receives production
traffic": replay a sample of realistic recent production requests (from
logs, a shadow-traffic mirror, or a synthetic warm-up script) against the
green environment before cutover to populate caches and pre-establish
connection pool entries, and gate the actual cutover on a readiness
signal that reflects warmth (pool fill level above a threshold, cache
hit rate above a threshold) rather than mere liveness. Where the
platform supports it, prefer a gradual traffic ramp (1% -> 10% ->
50% -> 100%) over an instant flip, so the environment absorbs increasing
load while still warming rather than receiving full load on request one.

## Pitfalls
- Warming up with synthetic traffic that doesn't resemble the real
  request distribution (e.g. hitting only one cheap endpoint in a loop)
  warms the wrong cache entries and connection pool sizing, giving false
  confidence while the actual spike-causing paths stay cold.
- Over-provisioning the green environment's pool/cache sizes to mask the
  cold-start cost is treating the symptom, not the cause -- it increases
  baseline cost for every deploy and doesn't fix the underlying gap
  between "health check passed" and "actually warm," which will
  resurface the moment traffic patterns shift.

## Verify
Perform a cutover in a staging or low-traffic-hours production window
with connection pool and cache hit-rate dashboards open, and confirm both
metrics are already at or near steady-state values (not near zero) at the
moment traffic switches, with no corresponding latency/error spike in the
minutes immediately following.
