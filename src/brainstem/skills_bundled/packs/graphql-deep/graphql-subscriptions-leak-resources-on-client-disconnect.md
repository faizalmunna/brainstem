---
name: graphql-subscriptions-leak-resources-on-client-disconnect
description: Server memory or open connections grow steadily over time because GraphQL subscription resources are never cleaned up when clients disconnect abruptly.
triggers: ["graphql subscription memory leak", "websocket subscriptions not cleaned up", "graphql server memory grows over time subscriptions", "subscription resolver still running after client left"]
permissions: ["READ"]
---

## Symptom
A GraphQL server offering real-time subscriptions (over WebSocket, SSE, or a similar transport) shows steadily increasing memory usage, growing counts of active subscription objects, or lingering connections/database listeners in monitoring dashboards that never come back down, correlated with the rate of clients connecting and disconnecting rather than with the number of currently-connected clients -- indicating cleanup on disconnect isn't happening, only cleanup on graceful unsubscribe is.

## Likely causes
1. **The subscription resolver's cleanup logic is only wired to a graceful `unsubscribe` message**, but real clients disconnect far more often via network drops, tab closes, mobile app backgrounding, or process kills that never send a graceful unsubscribe -- and the server-side async iterator or event listener behind the subscription is only torn down in the `return()` method of the async generator, which some transport implementations don't reliably call on abrupt disconnect.
2. **Each subscription resolver registers a listener on a shared event emitter, pub/sub channel, or database change stream (e.g. Postgres `LISTEN/NOTIFY`, Redis pub/sub) without a corresponding `removeListener`/unsubscribe call tied to connection close**, so every dropped connection leaves an orphaned listener that keeps the underlying resource (and its captured closure state, including references to the disconnected client's context) alive indefinitely.
3. **The WebSocket server layer and the GraphQL subscription layer are wired independently**, and the WebSocket `close`/`error` event isn't propagated to the GraphQL execution context that owns the subscription's async iterator, so the two layers disagree about whether the subscription is still active.
4. **A heartbeat/keepalive mechanism is missing**, so half-open TCP connections (client crashed or lost network without a clean FIN) are never detected as dead by the server at all, and the subscription is kept alive server-side indefinitely because, from the server's perspective, nothing has told it the client is gone.

## Diagnose
- Track a metric for active subscription count / active pub-sub listener count over time in a staging environment, and simulate abrupt client disconnects (killing the client process or forcibly closing the WebSocket without sending a close frame) rather than graceful unsubscribes -- confirm whether the metric drops after disconnect or keeps climbing.
- Check the subscription resolver's async generator implementation for a `return()` or `finally` block that unregisters the underlying listener, and check whether the GraphQL server library in use (graphql-ws, subscriptions-transport-ws, Apollo Server's subscription support) actually guarantees calling it on ungraceful socket closure -- consult that library's docs specifically, since guarantees differ meaningfully between transport implementations and even between library versions.
- Inspect whether a heartbeat/ping-pong mechanism is configured at the WebSocket layer; if absent, half-open connections can remain "open" from the server's perspective for a long time (until an OS-level TCP timeout), during which the subscription resource is never released.
- For pub/sub-backed subscriptions (Redis, Postgres LISTEN/NOTIFY), directly query the pub/sub backend's active subscriber/channel count and compare it against your application's actual active WebSocket connection count -- a persistent gap confirms orphaned backend listeners.

## Fix
Tie subscription resource lifetime explicitly to connection lifetime at every layer, not just to the GraphQL-level unsubscribe message:
- Ensure the async iterator backing each subscription resolver unregisters its listener/cleans up its resource in a `finally` block (or the iterator's `return()` method) so it runs regardless of whether the generator was iterated to graceful completion, thrown into, or abandoned by early termination -- and confirm your specific WebSocket/subscription transport library actually invokes this on abrupt close by checking its documented guarantees or, if in doubt, testing directly.
- Enable heartbeat/ping-pong at the WebSocket layer with a reasonable timeout (e.g. ping every 30s, drop after two missed pongs) so half-open connections from crashed clients or lost networks are detected and closed server-side within a bounded time, triggering the same cleanup path as an explicit disconnect.
- Wire the transport-level close/error event directly to the GraphQL execution context's cancellation, so a WebSocket close reliably signals every active subscription associated with that connection to tear down, rather than relying on each subscription resolver to separately detect disconnection.
- For pub/sub-backed subscriptions, unsubscribe from the backend channel specifically when the last local listener for that channel is removed (reference-counting shared channels across multiple subscribers) so the backend connection itself is also released once truly unused, not just the in-process listener.

## Pitfalls
Relying solely on a periodic garbage-collection sweep (e.g. "clean up any subscription older than N hours") as the primary cleanup mechanism instead of fixing per-connection cleanup treats the symptom, not the cause -- it caps the leak's growth rate but doesn't eliminate it, delays detection of the underlying bug, and can itself accidentally kill legitimately long-lived subscriptions (e.g. a dashboard left open for a full workday) if the sweep threshold isn't generous enough.

## Verify
In a load test, open a large number of subscriptions and then kill the client connections abruptly (not gracefully) rather than closing them cleanly, then confirm server-side active-subscription and pub/sub-listener counts return to baseline within the configured heartbeat timeout window, with no continued growth across repeated connect/abrupt-disconnect cycles.
