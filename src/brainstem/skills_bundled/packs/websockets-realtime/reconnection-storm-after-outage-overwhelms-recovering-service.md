---
name: reconnection-storm-after-outage-overwhelms-recovering-service
description: A brief WebSocket service disruption causes nearly all clients to disconnect and reconnect at once, and the resulting reconnection storm re-crashes the service just as it recovers.
triggers: ["service crashes again right after we fixed it", "reconnect storm", "thundering herd after outage", "all clients reconnected at the same time and took us down again", "deploy caused a wave of reconnects that overloaded the server"]
permissions: ["READ"]
---

## Symptom
A WebSocket-serving fleet has a short outage or restart (a deploy, an
OOM kill, a load balancer blip) lasting only seconds to a couple of
minutes. Immediately after it comes back, CPU/connection-accept rate
spikes far higher than steady-state traffic ever was, and the service
falls back over -- sometimes worse than the original incident. Metrics
show a near-vertical wall of new connection attempts landing in the
same few-hundred-millisecond window right as health checks start
passing again, rather than the gradual ramp normal traffic would show.

## Likely causes
1. **Every client uses the same fixed reconnect delay** (e.g. "wait 1
   second, then reconnect"), so a population of clients disconnected by
   the same outage all wake up and dial back in within the same narrow
   window -- the outage synchronized their retry clocks even though
   they were never coordinated with each other.
2. **No jitter on the retry delay**, so even clients using exponential
   backoff step through the *same* sequence of delays in lockstep (all
   waiting exactly 1s, then all waiting exactly 2s, etc.), regenerating
   a synchronized spike at each retry tier instead of spreading load.
3. **The server accepts connections before it's actually ready to serve
   them** -- a load balancer or health check marks an instance healthy
   as soon as the TCP/HTTP port is listening, before caches are warm,
   auth/session lookups are fast, or downstream dependencies (session
   store, pub/sub backend) have reconnected -- so the first wave of
   reconnects hits a technically-up but practically-overloaded instance
   and knocks it back down, restarting the cycle.
4. **Reconnect logic re-does expensive per-connection setup** (full
   auth handshake, re-fetching large initial state/snapshot payloads,
   re-subscribing to many channels) rather than a cheap resume, so the
   *cost per reconnection* is much higher than the cost of an
   already-established connection, meaning even a normal connection
   count reconnecting simultaneously produces an abnormal load spike.

## Diagnose
- Pull connection-accept-rate and CPU/memory graphs for the outage
  window: a symptom-confirming shape is a flat baseline, a drop to
  zero during the outage, then a spike far above baseline in the first
  few seconds after recovery, decaying over the following seconds to
  minutes -- that decay shape is the herd draining, not organic growth.
- Check actual client reconnect code for the delay calculation: grep
  for the reconnect handler and confirm whether it's `setTimeout(fn,
  fixedMs)` versus an exponential value, and whether that value has any
  randomization applied (`Math.random()` or similar) before use.
- Compare timestamps of reconnect attempts from a sample of clients
  (from access logs or a connection-attempt metric tagged with client
  ID) -- if a large fraction cluster within the same 1-2 second bucket
  repeatedly at each retry tier, that confirms lockstep retries rather
  than jittered ones.
- Check what the load balancer/orchestrator's health check actually
  probes (a raw TCP connect vs. an application-level readiness
  endpoint that checks downstream dependencies) -- a health check that
  only verifies the process is listening will mark an instance healthy
  before it can actually absorb the reconnect wave.
- Measure and compare the cost of a fresh connection's setup path vs.
  a steady-state connection's per-message cost (time or DB/auth calls
  per connect) -- if connection setup does multiple round trips or
  large payload sends, the herd's cost is a multiple of connection
  count, not equal to it.

## Fix
Treat reconnection as a load-generating event that must be
deliberately spread out, on both ends:
- On the client, use exponential backoff *with full jitter*: pick the
  next delay as a random value between 0 and
  `min(maxDelay, baseDelay * 2^attempt)`, not the deterministic
  exponential value itself -- jitter is what actually breaks the
  lockstep between independently-disconnected clients, exponential
  growth alone only spaces out one client's own retries.
- On the server, make the health check gate on real readiness --
  downstream dependencies connected, caches warmed, a synthetic
  request served successfully -- not just "port is open," so the load
  balancer doesn't route the reconnect wave to instances that can't
  yet absorb it.
- Add connection-admission control: a per-instance or per-second cap on
  new connection accepts (queue or reject with a `Retry-After`-style
  hint beyond the cap) so that even an unjittered herd can only land at
  a bounded rate per instance, converting an unbounded spike into a
  controlled ramp.
- Where the protocol allows it, make reconnection cheap: support a
  resume/reattach flow that skips full re-auth and full state
  re-fetch for a client that dropped and reconnected within a short
  window, so the herd's cost per connection collapses back toward
  steady-state cost instead of being a multiple of it.

## Pitfalls
- Adding jitter only to the client's *first* retry and reverting to a
  fixed interval afterward still produces synchronized retries at
  every subsequent tier -- jitter has to be recalculated fresh for
  every attempt, not applied once.
- Capping server-side connection accept rate without also giving
  clients a way to tell "rejected due to overload, retry later" apart
  from "auth failed, don't retry" causes clients on a tight retry loop
  to hammer the cap indefinitely instead of backing off further.
- Rolling out a fix to the fan-out/session layer as a single big-bang
  deploy across the whole fleet at once recreates exactly the outage
  this skill is about -- roll deploys in waves with connection draining
  (see the connection-draining skill in this pack) rather than
  restarting every instance simultaneously.

## Verify
In a staging environment, simulate an outage by killing or network-
partitioning a meaningful fraction of server instances while under a
realistic connected-client load, then restore them and watch the
connection-accept-rate graph: with the fix in place, the post-recovery
acceptance curve should ramp up over tens of seconds to minutes rather
than spiking as a near-vertical wall, and no instance's CPU/connection
count should exceed its normal operating ceiling during the recovery
window.
