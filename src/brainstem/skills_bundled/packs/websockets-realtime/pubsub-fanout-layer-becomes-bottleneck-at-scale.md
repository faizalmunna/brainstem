---
name: pubsub-fanout-layer-becomes-bottleneck-at-scale
description: The pub/sub backend used to fan out messages across horizontally scaled WebSocket server instances becomes a throughput bottleneck or single point of failure as connection count grows.
triggers: ["messages delayed across server instances", "pubsub backend maxed out", "fanout is the bottleneck", "redis pubsub cpu pegged", "cross-instance broadcast is slow at scale"]
permissions: ["READ"]
---

## Symptom
A WebSocket service scaled horizontally across multiple instances
relies on a pub/sub backend (Redis pub/sub, NATS, Kafka, a managed
message broker) so a message published on one instance reaches
clients connected to any instance. At moderate scale this works fine;
past some connection or message-rate threshold, cross-instance message
delivery latency climbs, the pub/sub backend's CPU or network
saturates, or the backend itself becomes a recurring outage source --
and because every server instance depends on it, its degradation looks
like a global outage rather than a single-instance problem.

## Likely causes
1. **Fan-out is O(subscribers) work funneled through one logical
   broker/channel structure that doesn't itself scale horizontally**
   (e.g. a single Redis instance's pub/sub, which is single-threaded
   for command processing) -- as total message volume times average
   fan-out size grows, the broker's single processing path saturates
   well before any individual WebSocket server instance does.
2. **Every message is broadcast to every server instance regardless of
   whether that instance holds any relevant subscribers**, because
   channels are coarse (one global channel, or one per broad topic
   like "all chat") rather than scoped to actual subscriber
   distribution -- instances waste CPU deserializing and discarding
   messages meant for connections they don't hold, and the broker
   pays the full fan-out cost redundantly for every instance whether
   or not it's needed there.
3. **No backpressure or batching between the pub/sub layer and the
   per-connection send path**, so a burst on the broker translates
   directly into a synchronized burst of sends across every instance
   at once, and if that in turn hits the per-connection queue limits
   (see the slow-client skill in this pack) the fan-out spike cascades
   into connection drops fleet-wide rather than being absorbed.
4. **The pub/sub backend is a single point of failure with no
   degradation path** -- if it becomes unavailable, WebSocket servers
   either block/queue trying to publish (backing up upstream producers
   too) or silently drop all cross-instance delivery, and because
   every instance shares the same backend, its failure is correlated
   across the whole fleet rather than isolated to one instance.

## Diagnose
- Graph the pub/sub backend's own resource usage (CPU, network
  throughput, command/message rate) against total connected-client
  count and message rate -- if the backend's CPU tracks close to 100%
  while individual WebSocket instances have headroom, the bottleneck
  is confirmed to be the fan-out layer, not the connection-handling
  layer.
- Check channel/topic granularity in the code that publishes and
  subscribes: count how many distinct channels exist relative to how
  many logical subscriber groups exist -- a ratio far below 1
  (many subscriber groups sharing very few channels) indicates
  over-broad fan-out.
- Measure end-to-end cross-instance delivery latency directly: publish
  a timestamped message from instance A and record when a client
  connected to instance B receives it, under realistic load -- rising
  p99 latency here specifically (versus same-instance delivery
  staying fast) isolates the fan-out hop as the source of delay.
- Check what happens on the WebSocket servers when the pub/sub client
  library reports a connection error or backpressure from the broker
  (some clients expose a callback or promise rejection for this) --
  confirm whether publishes block, queue in memory, or are dropped,
  since each has a different failure signature under a broker outage.
- Review the broker's own scaling model (a single Redis pub/sub
  instance has no built-in partitioning for pub/sub; Kafka partitions
  by key; NATS supports clustering) against how the application
  actually uses it, since the fix differs by which of these gaps
  applies.

## Fix
Treat the fan-out layer as a scaling dimension in its own right, not
an implementation detail behind the WebSocket servers:
- Scope channels to actual subscriber locality where possible (per
  room/topic/shard rather than one global channel) so a given message
  only reaches the broker traffic and the instances that actually have
  subscribers for it, cutting redundant fan-out work at both the
  broker and the receiving instances.
- Choose a backend whose fan-out path scales horizontally with load --
  Redis Cluster does not parallelize pub/sub across shards the way it
  does keyspace commands, so for high fan-out volume prefer a
  broker built for partitioned fan-out (Kafka with partitioning by
  room/topic key, NATS clustering/JetStream, or a managed pub/sub
  service designed for this) over a single pub/sub node.
- Batch and coalesce outgoing cross-instance messages where the
  application semantics allow it (e.g. combine multiple rapid updates
  to the same resource into one message per short interval) so
  message rate through the broker doesn't scale linearly with the
  finest-grained event rate.
- Design an explicit degraded mode for broker unavailability: same-
  instance delivery (clients connected to the instance that produced
  the message) should keep working even if cross-instance fan-out is
  down, so a broker outage degrades reach rather than taking down
  message delivery entirely.

## Pitfalls
- Splitting into more channels without also reconsidering subscriber
  distribution can just move the bottleneck from broker CPU to
  connection/subscription overhead if the library re-subscribes
  expensively per channel change -- measure both channel fan-out cost
  and subscription-management cost before assuming finer granularity
  is free.
- Switching brokers (e.g. Redis pub/sub to Kafka) without addressing
  message ordering and at-least-once delivery semantics can introduce
  duplicate or reordered message delivery to clients that the
  application wasn't previously handling -- pair a broker migration
  with idempotency/ordering handling on the receiving side (see the
  message-ordering skill in this pack).
- Assuming the fan-out layer scales because a single high-throughput
  benchmark passed -- benchmark with the actual subscriber fan-out
  ratio (messages-per-publish times average subscriber count) the
  production topology produces, since a broker that handles high
  publish rate with low fan-out can still choke on low publish rate
  with very high fan-out per message.

## Verify
Load-test with a subscriber distribution and message rate matching
production's actual fan-out ratio (not just raw connection count),
and confirm cross-instance delivery p99 latency stays within the
target SLA as connection count scales up, the broker's CPU/network
utilization stays below saturation at the target scale, and killing
the pub/sub backend in a controlled test causes same-instance delivery
to keep working (even if cross-instance delivery pauses) rather than
taking down message delivery fleet-wide.
