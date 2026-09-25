---
name: grpc-streaming-backpressure-overwhelms-consumer
description: A gRPC streaming RPC keeps sending messages faster than the receiver can process them, causing unbounded memory growth or a consumer crash.
triggers: ["grpc stream out of memory", "server streaming overwhelms client", "grpc consumer falling behind producer", "unbounded buffer grpc stream", "streaming rpc memory leak growing queue"]
permissions: ["READ"]
---

## Symptom
A server-streaming (or client-streaming) RPC works fine in testing with
small volumes, but in production the receiving side's memory usage grows
continuously for the duration of a long stream, sometimes ending in an
out-of-memory crash or a sharp latency spike -- while the sending side
reports nothing unusual, because from its perspective it's just
successfully calling `Send()` repeatedly. The receiver is falling behind
the producer and the gap is being absorbed by an ever-growing buffer
somewhere in the pipeline instead of pushing back on the sender.

## Likely causes
1. **The receiving application reads messages off the stream into an
   application-level queue faster than it can process them**, decoupling
   the gRPC-level flow control (which does exist at the HTTP/2 layer)
   from the actual processing rate -- gRPC/HTTP/2 flow control governs
   bytes on the wire, not whatever unbounded in-process queue the
   application code puts between `Recv()` and the actual handler logic.
2. **The consumer processes messages asynchronously and fires off
   unbounded concurrent work per message** (spawning a goroutine/task per
   received item with no concurrency limit) -- the receive loop itself
   stays fast, masking that the real processing is falling behind, until
   the number of in-flight tasks exhausts memory or downstream resources
   (DB connections, thread pool).
3. **The sender doesn't consult any signal from the receiver before
   producing the next message** -- e.g. a server streaming results from a
   fast in-memory generator or a database cursor with a large prefetch,
   pushing messages onto the stream continuously without ever checking
   whether the client is keeping up, relying entirely on transport-level
   flow control to eventually block `Send()`, which only kicks in once
   HTTP/2 window sizes are exhausted -- often after a large amount has
   already been buffered.
4. **HTTP/2 flow control windows are configured unusually large**
   (increased to "fix" an unrelated throughput problem) -- this raises
   the amount of data that can be in flight before the transport itself
   starts to push back, which increases the size of the memory spike
   before backpressure ever kicks in, rather than preventing it.

## Diagnose
- Measure the rate of `Recv()` calls versus the rate at which received
  messages are actually fully processed (not just dequeued) -- if
  there's an application-level queue in between, instrument its length
  over time during a long stream and confirm whether it grows unboundedly
  rather than staying roughly flat.
- Check for unbounded concurrency on the consumer side: count in-flight
  processing tasks/goroutines spawned per received message and confirm
  whether that count is bounded by a worker pool/semaphore or grows
  linearly with messages received.
- On the sender side, check whether `Send()` calls ever actually block
  under the observed load (a blocking `Send()` is flow control doing its
  job) versus always returning immediately -- if it never blocks even
  while the consumer is visibly falling behind, the transport-level
  window is likely oversized relative to how far behind the consumer can
  get, or intermediate buffering is hiding the real state.
- Profile heap growth during a sustained stream (language-appropriate
  heap profiler) and confirm the growing allocation is the
  application-level buffer/queue rather than an unrelated leak, to avoid
  chasing the wrong fix.

## Fix
- Process messages synchronously within the receive loop, or bound any
  asynchronous processing with a fixed-size worker pool/semaphore so the
  loop only calls `Recv()` again once there's capacity to handle the next
  message -- this makes the natural backpressure of "don't call `Recv()`
  yet" propagate back through gRPC's flow control to the sender's
  `Send()` calls, which will then genuinely block.
- On the producer side, for data sourced from something pull-based (a DB
  cursor, a file), pace production to roughly match consumption rather
  than eagerly buffering ahead -- pull the next chunk only after the
  previous `Send()` call returns, rather than prefetching far ahead of
  what's been sent.
- Explicitly bound any application-level queue between the network read
  and the processing logic, with a policy for what happens when it's
  full (block the receive loop -- correct backpressure -- rather than
  dropping messages or growing unbounded).
- Size HTTP/2 flow control windows deliberately based on measured
  acceptable in-flight data, not maximized by default, so the transport
  itself provides a meaningful backpressure signal at a bounded memory
  cost rather than only after a large buffer has already accumulated.

## Pitfalls
- "Fixing" the memory growth by just adding a queue size cap that drops
  or silently discards messages when full -- this trades an OOM crash for
  silent data loss, which is worse for correctness even if it looks
  healthier in a memory graph.
- Increasing HTTP/2 flow control window sizes to "fix" the symptom
  because it makes throughput numbers look better in a synthetic
  benchmark -- this increases the amount of unprocessed data that can
  pile up before any pushback occurs, making a real backpressure problem
  larger, not smaller.
- Spawning one task per message with no concurrency limit to "process
  messages in parallel for speed" -- without a bound, this turns a
  bounded-memory backpressure problem into an unbounded one, since
  concurrency itself becomes the runaway resource.

## Verify
Run the stream against a consumer deliberately throttled to process at a
known fixed rate (e.g. inject an artificial per-message delay) well below
the producer's natural rate, and confirm that the producer's `Send()`
calls measurably slow down or block to match (observable backpressure)
while memory usage on the consumer stays bounded and roughly flat for the
duration of the stream, rather than growing linearly with elapsed time.
