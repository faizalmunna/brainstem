---
name: slow-client-causes-unbounded-per-connection-send-queue-growth
description: A server-side per-connection outgoing message buffer grows without limit when a slow or stalled WebSocket client can't keep up, eventually exhausting server memory.
triggers: ["server memory keeps growing with connected clients", "slow client causes memory leak", "outgoing buffer grows unbounded", "OOM with many websocket connections", "bufferedAmount keeps increasing"]
permissions: ["READ"]
---

## Symptom
Server-side memory usage climbs steadily in proportion to the number
of connected WebSocket clients and the volume of messages being
pushed to them, eventually leading to an OOM kill or severe GC
pressure -- but only under real traffic with a mix of client
conditions (mobile clients on flaky connections, browser tabs
backgrounded and throttled), not in load tests using only
fast/local clients. Killing a handful of specific slow-seeming
connections often immediately frees a disproportionate amount of
memory.

## Likely causes
1. **No backpressure check before calling send()** -- the server calls
   `ws.send(msg)` for every outgoing message regardless of whether the
   underlying socket can currently accept more data, so when the
   client (or the network path to it) can't drain fast enough, the
   WebSocket library's internal send buffer for that connection queues
   messages indefinitely rather than the server ever slowing down.
2. **No maximum buffered-bytes limit per connection**, so there's no
   point at which the server decides "this client is too far behind,
   stop sending and drop/close it" -- one stalled client can
   accumulate an unbounded queue for as long as the connection stays
   open, and with many such clients the aggregate memory is
   effectively unbounded.
3. **A single slow subscriber on a fan-out/broadcast path holds up or
   silently accumulates for everyone** -- broadcast code that iterates
   subscribers and calls `send()` synchronously per connection can
   either block the whole broadcast loop on one slow socket, or (more
   commonly with async sends) queue a growing backlog for that one
   subscriber every broadcast tick while every other subscriber drains
   fine, so the problem is invisible in aggregate metrics until that
   one connection's queue is examined.
4. **The application buffers business-level messages in its own array
   "just in case," separate from the OS/library socket buffer**, so
   even a library that does respect backpressure at the socket level
   never gets the signal, because the application layer keeps
   producing and stockpiling messages it hasn't even attempted to send
   yet.

## Diagnose
- Check `ws.bufferedAmount` (or the equivalent in the library in use)
  across connections under load -- a small number of connections with
  `bufferedAmount` many orders of magnitude larger than the rest is
  the direct signature of this issue; graph it per-connection, not
  just aggregated, since aggregation hides the few pathological
  connections behind many healthy ones.
- Check whether outgoing sends are gated on `bufferedAmount` or the
  library's write-callback/promise before the *next* send is issued
  for that same connection, or whether the code fires sends in a tight
  loop with no regard for completion.
- Reproduce directly: connect a test client and artificially stall its
  read loop (pause consuming incoming frames) while the server pushes
  messages to it at a steady rate; watch that connection's
  `bufferedAmount` and the server's overall RSS -- unbounded growth in
  both while the stalled client sits idle confirms the issue.
- For fan-out/broadcast paths, log or trace per-subscriber send
  duration and queue depth during a broadcast, not just total
  broadcast duration -- a bimodal distribution (most subscribers
  finish in microseconds, a few take seconds or never complete) points
  at the "one slow subscriber" variant rather than a general
  under-provisioning problem.
- Take a heap snapshot during elevated memory and look for the
  concentration of retained size -- confirm it's held by connection/
  socket-buffer objects (or an application-level outbox array) rather
  than an unrelated leak, since the fix differs.

## Fix
Establish an explicit, enforced ceiling on how far behind any single
connection is allowed to get, and act deterministically once it's hit:
- Check `bufferedAmount` (or equivalent) before every send; if it
  exceeds a chosen threshold (tuned to the message size and rate for
  the application, not an arbitrary constant), skip sending
  non-critical messages to that connection, coalesce/replace
  superseded updates (e.g. keep only the latest price tick instead of
  queuing every one), or close the connection outright with a specific
  close code so the client and any monitoring can distinguish
  "disconnected for being too slow" from a normal disconnect.
- Make fan-out asynchronous and isolated per subscriber -- one slow
  subscriber's backlog must not block or delay delivery to any other
  subscriber; use a per-connection queue with its own bound rather
  than a single shared loop that waits on each send in turn.
- For data where only the latest value matters (presence, live scores,
  cursor positions), replace queuing entirely with a "latest wins"
  slot per connection instead of an ever-growing queue -- this bounds
  memory to O(1) per connection regardless of how far behind the
  client falls.
- Emit a metric and/or structured log every time a connection is
  dropped or throttled for exceeding the buffer threshold, so this
  becomes an observable, tunable operational signal rather than a
  silent internal decision.

## Pitfalls
- Setting the buffered-bytes threshold too low for the application's
  normal message size/burst pattern causes healthy clients on merely
  slightly slower connections (mobile, higher latency) to be
  disconnected constantly, trading a memory problem for a churn/
  reliability problem -- tune the threshold against real traffic
  percentiles, not a guess.
- Silently dropping messages for a throttled connection without any
  application-level recovery (a resync/snapshot mechanism on
  reconnect) leaves that client's state permanently inconsistent even
  after it reconnects -- pair backpressure-driven drops with a way for
  the client to detect it missed messages and request a fresh
  snapshot.
- "Fixing" this by simply increasing server memory or instance size
  delays the failure without bounding it -- the queue is still
  unbounded, it just takes longer and more slow clients to trigger the
  same OOM.

## Verify
Under load, connect a deliberately slow/stalled test client alongside
many normal ones and confirm: that one connection's `bufferedAmount`
plateaus at or near the configured threshold rather than growing
without bound, the connection is either throttled or cleanly closed
once the threshold is exceeded, every other concurrently connected
client continues receiving messages at normal latency throughout, and
overall server RSS stays flat rather than climbing for the duration of
the stalled client's connection.
