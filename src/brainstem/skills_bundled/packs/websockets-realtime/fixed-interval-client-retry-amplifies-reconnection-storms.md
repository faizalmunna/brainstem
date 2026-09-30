---
name: fixed-interval-client-retry-amplifies-reconnection-storms
description: Client-side WebSocket reconnection logic uses a fixed retry interval instead of exponential backoff with jitter, synchronizing retries into repeated load spikes on the server.
triggers: ["reconnect logic retries every 5 seconds no matter what", "client hammers the server on reconnect", "setInterval reconnect loop", "reconnect storm from client retry logic", "server gets hit with retries in bursts"]
permissions: ["READ"]
---

## Symptom
Client applications reconnect on a rigid, unchanging schedule (e.g.
"if disconnected, try again every 3 seconds") regardless of how many
times the previous attempt failed. Server-side connection-attempt
metrics show a sawtooth or comb pattern -- sharp periodic spikes at
multiples of the retry interval -- during any period where the server
is degraded or unreachable, and the server's own load during an outage
is dominated by rejected/failed connection attempts rather than
genuine new traffic, sometimes preventing the server from recovering
at all ("it never gets a quiet moment to come back up").

## Likely causes
1. **The reconnect handler uses `setInterval` or a hardcoded
   `setTimeout(fn, N)`** with the same `N` on every attempt, with no
   growth as failures accumulate -- a reasonable interval for "server
   had a one-off blip" becomes a sustained hammering pattern for "server
   has been down for two minutes."
2. **No randomization is applied to the interval**, so every client
   instance that disconnected around the same moment (which is common,
   since they were often disconnected by the same server-side event)
   continues retrying in lockstep indefinitely, not just on the first
   attempt.
3. **No cap on retry attempts or escalation to a different behavior**
   (e.g. surfacing an offline state to the user, falling back to
   polling) -- the client retries forever at the same aggressive rate
   even during an extended outage, so total retry traffic across the
   client population never decreases even as the outage drags on.
4. **Reconnect logic is duplicated or triggered from multiple places**
   (e.g. both a `close` event handler and a separate heartbeat-timeout
   handler each independently schedule a reconnect) -- causing a
   single client to run multiple concurrent retry loops, multiplying
   its contribution to server load beyond what a single well-behaved
   client would generate.

## Diagnose
- Read the client's reconnect implementation directly and check the
  delay calculation: a literal constant, or a `setInterval` with fixed
  period, is the direct signature; also check whether any jitter
  (`Math.random()` or similar) is applied to whatever delay is used.
- During a real or simulated server outage, capture the timestamps of
  a single client's reconnect attempts and plot the intervals between
  them -- a constant, unchanging gap confirms fixed-interval retry; a
  growing-but-still-clustered-across-clients gap confirms
  backoff-without-jitter.
- On the server side, graph connection-attempt rate (not just
  successful connections) during a past or simulated outage -- a comb/
  sawtooth pattern with sharp periodic peaks is the server-side
  fingerprint of synchronized fixed-interval retries across the client
  population.
- Check for multiple independent reconnect triggers in the client
  codebase (search for all call sites that schedule a reconnect) and
  confirm whether guards exist to prevent more than one reconnect loop
  running concurrently for the same logical connection.
- Check whether there's any maximum retry count or backoff ceiling --
  attempt a sustained multi-minute simulated outage and confirm
  whether the client ever changes behavior (slows down, gives up,
  surfaces an error state) or retries identically indefinitely.

## Fix
Replace fixed-interval retry with capped exponential backoff plus full
jitter, and give it an explicit ceiling and terminal state:
- Compute each retry delay as `random(0, min(maxDelay, baseDelay *
  2^attempt))`, incrementing `attempt` on each failure and resetting it
  to zero only after a successfully established and stable (not
  immediately dropped again) connection -- the jitter is what
  desynchronizes clients that failed at the same moment, and the cap
  keeps delay from growing unbounded over a long outage.
- Ensure exactly one reconnect loop can be active per logical
  connection -- centralize scheduling in one place and guard against
  the `close` handler and any heartbeat-timeout handler both
  independently kicking off a new attempt.
- After some number of consecutive failures, surface an explicit
  degraded/offline state to the rest of the application (and, where
  relevant, the user) rather than retrying silently forever at the
  capped rate -- this both improves UX and gives an operational signal
  distinct from "still trying."
- Where the server can communicate it (a specific close code, or a
  `Retry-After`-equivalent field in a rejection), let the client honor
  a server-suggested delay instead of purely client-driven backoff, so
  the server can actively shape retry timing during a known recovery
  window.

## Pitfalls
- Applying jitter as a fixed random offset added to a fixed base delay
  (e.g. `3000 + random(0, 500)`) rather than randomizing across the
  full exponential range still leaves most of the delay's mass
  concentrated at the same point, providing far less desynchronization
  than full jitter over the whole computed range.
- Resetting the backoff `attempt` counter as soon as the connection
  event fires, rather than after it's been stable for some minimum
  duration, means a connection that repeatedly connects and
  immediately drops again (e.g. because the server is still overloaded
  and drops it right away) never actually backs off, since each
  fleeting success resets it back to the fastest retry tier.
- Backing off too aggressively with too low a retry ceiling for an
  interactive application can make genuine brief blips feel like long
  outages to the user -- tune `maxDelay` against how quickly a real
  transient blip typically resolves versus how long a real outage
  typically lasts.

## Verify
Simulate a multi-minute server outage against a test client
population and confirm: individual clients' retry intervals visibly
grow across successive attempts up to the configured cap, plotting
all clients' attempt timestamps together shows a spread-out
distribution rather than sharp periodic spikes, and total connection-
attempt rate hitting the server during the outage stays well below the
server's normal connection-accept capacity rather than scaling with
the disconnected client count.
