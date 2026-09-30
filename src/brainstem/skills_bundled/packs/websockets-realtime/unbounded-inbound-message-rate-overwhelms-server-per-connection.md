---
name: unbounded-inbound-message-rate-overwhelms-server-per-connection
description: A single WebSocket client sending messages faster than the server can process them exhausts server-side resources because there is no inbound rate limit per connection.
triggers: ["one client can slow down the whole server", "no rate limit on incoming websocket messages", "malicious client floods the server", "server CPU spikes from one connection", "runaway client causes latency for everyone else"]
permissions: ["READ"]
---

## Symptom
A single misbehaving, buggy, or malicious client -- one with a tight
client-side retry/emit loop, a bug that resends the same event
repeatedly, or deliberate abuse -- causes server-wide latency
degradation or CPU saturation, even though it's only one connection
out of many. Removing or throttling that one connection immediately
restores normal service for everyone else, which distinguishes this
from a genuine capacity problem, but nothing in the server currently
detects or limits the pattern before it reaches that point.

## Likely causes
1. **No per-connection inbound rate limit exists at all** -- the
   server's `message` handler processes every inbound frame as fast as
   it arrives with no counter or throttle tied to the sending
   connection, so a connection sending at an abnormal rate consumes a
   proportionally abnormal share of server processing time with
   nothing pushing back on it.
2. **Each inbound message triggers disproportionately expensive work**
   (a database write, a broadcast to a large room, a synchronous
   computation) relative to how cheap it is for a client to send one,
   so the *cost asymmetry* between sending and handling a message means
   even a moderate inbound rate from one connection can dominate
   server capacity that many other connections share.
3. **Rate limiting exists at the HTTP/REST layer (a standard
   middleware) but was never extended to the WebSocket message-handling
   path**, since WebocketSocket messages don't go through the same
   request pipeline that carries the existing rate-limit middleware --
   leaving the real-time path completely unprotected even though the
   team believes rate limiting is "already handled."
4. **Backpressure is handled for outbound messages (see this pack's
   slow-client skill) but nothing analogous exists for inbound** -- the
   two directions are easy to conflate, but protecting against a slow
   *receiver* does nothing to protect against a fast, aggressive
   *sender*, and teams that fixed one sometimes assume the other is
   covered by the same change.

## Diagnose
- Check the `message`/inbound event handler for any rate-limiting or
  counting logic keyed by connection -- absence of any such check is
  the first thing to confirm.
- Reproduce directly: write a test client that sends messages in a
  tight loop with no delay and measure both that connection's own
  processing latency and other concurrent connections' latency on the
  same server instance -- a sharp latency increase for *unrelated*
  connections while the flooding connection runs confirms shared-
  resource contention caused by one connection.
- Check whether existing rate-limiting middleware in the codebase is
  scoped to the HTTP router only (look at where it's registered) and
  confirm the WebSocket upgrade/message path is a separate code path
  that middleware never touches.
- Measure the actual cost of handling one inbound message under
  realistic conditions (time or resource cost of whatever the handler
  does -- a DB write, a broadcast, a computation) and compare it to how
  fast a client can legitimately produce them, to judge how large the
  cost asymmetry in cause 2 actually is for this application.
- Check server logs/metrics for whether any past incidents correlate
  with a single connection's message rate spiking -- if monitoring
  doesn't currently break down inbound rate per connection, that gap
  itself is worth noting since it makes this class of incident hard to
  diagnose quickly in the future.

## Fix
Apply the same rate-limiting discipline to inbound WebSocket traffic
that would be expected on any other server-facing input path:
- Implement a per-connection inbound rate limit (a token bucket or
  sliding window keyed by connection ID, user ID, or IP as
  appropriate) inside the message handler itself, independent of any
  HTTP-layer middleware, since the WebSocket message path doesn't run
  through that pipeline.
- Choose the limit based on the legitimate use case's real message
  rate plus reasonable headroom, not an arbitrary round number --
  measure actual client behavior for the feature in question (typing
  indicators, cursor updates, chat messages each have very different
  natural rates) and set the limit against that baseline.
- On exceeding the limit, respond deterministically -- drop excess
  messages, queue with a cap and then drop, or close the connection
  with a specific code for repeat offenders -- rather than letting
  the handler process everything regardless, and emit a metric each
  time the limit triggers so sustained abuse is visible operationally.
- Where the cost asymmetry (cause 2) is large, consider decoupling
  expensive downstream work from the inbound message rate entirely --
  queue inbound events into a bounded work queue processed at a
  controlled rate, rather than doing the expensive work synchronously
  inline with each inbound frame.

## Pitfalls
- Setting a single global rate limit for all message types conflates
  cheap, high-frequency events (cursor position updates) with
  expensive, naturally-low-frequency ones (submitting a large form) --
  a limit tuned for one starves or fails to protect against abuse of
  the other; scope limits per message type where costs differ
  significantly.
- Rate-limiting by IP address alone in an environment with shared
  egress IPs (corporate NAT, mobile carrier NAT) can throttle many
  legitimate distinct users as if they were one abusive client --
  prefer a connection- or authenticated-user-scoped key when available.
- Silently dropping excess messages with no signal back to the client
  leaves a legitimate client that's simply misconfigured (a bug
  causing a retry loop) with no way to know it's being throttled,
  making the underlying client bug harder for its own team to
  discover -- send an explicit rate-limit notification frame where the
  protocol allows it.

## Verify
Run a test client that sends inbound messages well above the
configured limit while several other normal-rate clients are
connected to the same server instance, and confirm: the flooding
client's excess messages are dropped/throttled per the configured
policy (visible in server-side rate-limit metrics), the flooding
client itself receives a distinguishable signal (a rejection message
or close code) rather than silence, and the other concurrent
connections' message-handling latency stays within normal bounds
throughout the flood rather than degrading alongside it.
