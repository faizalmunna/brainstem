---
name: stale-permissions-persist-on-long-lived-websocket-session
description: A WebSocket connection keeps a user's original permissions for the life of the session even after their access is revoked or changed mid-connection.
triggers: ["revoked user can still receive updates over websocket", "permission change doesn't take effect until reconnect", "user removed from workspace but still connected", "banned user still getting realtime messages", "auth checked only at connect time"]
permissions: ["READ"]
---

## Symptom
A user's access is revoked, downgraded, or their session is
invalidated (removed from a workspace/channel, role changed, account
suspended, token revoked) through some other part of the system, but
they continue receiving real-time messages and can continue sending
actions over an already-open WebSocket connection as if nothing
changed -- sometimes for as long as that connection happens to stay
open, which for a long-lived WebSocket can be hours. The gap is
invisible in normal testing because most tests reconnect fresh after
any permission change, which coincidentally re-runs the auth check
and hides the bug.

## Likely causes
1. **Authorization is checked only during the initial handshake**
   (validating a token or session at connection time) and the result
   -- typically a set of allowed rooms/channels/scopes -- is cached in
   the connection's in-memory state for its entire lifetime, with
   nothing re-checking it against the current, authoritative
   permission state on any later action.
2. **No mechanism propagates permission-change events to already-open
   connections** -- the system that revokes access (an admin action,
   a subscription downgrade, a ban) updates the database but has no
   path to reach into the WebSocket layer and either update or
   terminate sessions belonging to the affected user, especially when
   that user's connection lives on a different server instance than
   the one handling the revocation.
3. **Room/channel subscriptions are treated as fire-and-forget grants**
   -- once a client subscribes to a channel it was authorized for at
   subscribe time, the server keeps delivering to that subscription
   without re-validating on each message, so even a per-message
   authorization check that exists elsewhere in the codebase (e.g. on
   a corresponding REST endpoint) never gets exercised for the
   WebSocket delivery path.
4. **Token expiry is enforced at the transport/library level but
   revocation is not** -- some setups do correctly disconnect on JWT
   expiry (because the library checks `exp` on a timer) but revocation
   before natural expiry (an explicit ban, a role change) uses a
   different code path that was never wired into the same
   enforcement mechanism.

## Diagnose
- Trace the code path for a connection's authorization: confirm
  whether the permission/role check happens only in the connection/
  handshake handler, or whether any per-message or periodic
  re-validation exists elsewhere.
- Reproduce directly: open a WebSocket session as a test user, then
  revoke that user's access through the normal admin/application path
  (not by killing their session directly), and observe whether the
  existing connection keeps receiving messages or is able to keep
  performing privileged actions afterward.
- Check whether revocation events are published anywhere the
  WebSocket layer could subscribe to them (an internal event bus, a
  database change stream, an explicit "kick user" admin action) or
  whether the revocation only ever touches the primary data store with
  no fan-out to connection state.
- If connections are distributed across multiple server instances,
  specifically check whether a revocation triggered against a user
  whose connection lives on a *different* instance than the one
  handling the revocation actually reaches that instance -- this is
  the case most likely to be silently missed even if same-instance
  revocation happens to work.
- Check logs/metrics for how long WebSocket connections typically stay
  open in production -- the longer the typical session, the larger the
  real-world exposure window this bug represents, which is useful for
  prioritizing the fix.

## Fix
Treat authorization as a continuously-valid property of the
connection, not a one-time grant established at connect time:
- Re-validate authorization at meaningful checkpoints beyond initial
  connect: on each subscribe/join-room action at minimum, and
  optionally on a periodic timer or on each inbound message for
  highly sensitive channels, comparing against the current
  authoritative permission state rather than a cached copy.
- Give the revocation path an explicit way to reach live connections:
  publish a "session invalidated" or "permissions changed for user X"
  event through the same pub/sub/fan-out mechanism used for regular
  messages (see this pack's fan-out skill), so every server instance
  -- not just the one that handled the revocation -- can check whether
  it holds a connection for that user and act on it.
- On receiving such an event, the instance holding the affected
  connection should either force-close it with a specific code the
  client maps to "re-authenticate" (triggering a clean reconnect that
  re-runs the full auth check) or, for a partial permission change,
  update the connection's cached permission set and unsubscribe it
  from any channels it's no longer authorized for.
- For short-session-lifetime tokens, keep enforcing expiry as a
  backstop even after adding revocation propagation -- the two
  mechanisms cover different cases (planned expiry vs. explicit
  revocation) and one doesn't substitute for the other.

## Pitfalls
- Force-closing a revoked user's connection without a specific close
  code/reason makes the client's generic reconnect logic just
  reconnect and immediately get denied at handshake -- fine
  functionally, but it produces a confusing reconnect-loop-then-error
  UX instead of an immediate, clear "access revoked" message; give
  revocation its own recognizable close code.
- Re-validating authorization on every single inbound/outbound message
  for all channels indiscriminately can add meaningful latency and
  load at scale -- reserve per-message re-validation for genuinely
  sensitive channels and rely on the subscribe-time-check-plus-
  revocation-event pattern for everything else.
- Only handling the same-instance case during development (since local
  dev often runs a single instance) and never testing cross-instance
  revocation propagation is how this bug survives into a horizontally
  scaled production deployment despite passing all local tests.

## Verify
With at least two server instances running behind the fan-out layer,
connect a test user to whichever instance does not handle the
subsequent revocation, revoke that user's access through the normal
application path, and confirm the connection is closed or its
subscriptions are pruned within one propagation-event round trip
(not "eventually, whenever they happen to reconnect"), and that any
further action attempted on the now-stale connection before it closes
is rejected rather than honored.
