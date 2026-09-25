---
name: producer-batching-latency-tradeoff-misconfigured
description: A Kafka producer's batching configuration causes either unexpectedly high per-message latency or poor throughput because linger and batch size settings don't match the actual workload.
triggers: ["kafka producer high latency", "kafka linger.ms causing delay", "producer batch size throughput low", "kafka message delay before send"]
permissions: ["READ"]
---

## Symptom

Either of two related symptoms: messages sent to Kafka show
unexpectedly high end-to-end latency even under low load (each message
seems to wait before actually being sent), or overall producer
throughput is much lower than the cluster should support despite the
producer sending messages continuously.

## Likely causes

- **`linger.ms` is set to a nontrivial value to encourage batching**
  (trading latency for throughput), but the workload is actually
  low-volume/latency-sensitive, so every message effectively waits up to
  the full linger duration before being sent, adding directly to
  end-to-end latency with no meaningful batching benefit at low volume.
- **`linger.ms` is left at its low/default value for a high-throughput
  workload**, so batches are sent before they fill up, producing many
  small requests instead of fewer, larger, more efficient ones --
  hurting throughput and increasing per-message overhead.
- **`batch.size` is set too small relative to actual message size and
  volume**, so batches fill and flush before `linger.ms` would have
  mattered anyway, capping potential batching efficiency regardless of
  the linger setting.
- **Compression is enabled with a CPU-expensive algorithm on a producer
  that's CPU-constrained**, adding latency from compression overhead
  that's mistaken for a batching/network issue.

## Diagnose

1. Check current `linger.ms`, `batch.size`, and compression type
   configuration against the workload's actual message rate and size.
2. Measure actual batch sizes being sent in practice (via producer
   metrics -- `batch-size-avg`, `record-queue-time-avg`) to see whether
   batches are filling up (indicating `batch.size` or `linger.ms` is
   the limiting factor) or being sent mostly empty (indicating `linger.
   ms` is too low relative to message rate for the desired batching
   behavior).
3. Break down end-to-end message latency into its components (queue
   time waiting for batch, network send time, broker processing time) to
   identify specifically which stage dominates.
4. Check producer-side CPU utilization if compression is suspected as a
   contributing latency factor.

## Fix

For latency-sensitive, lower-volume workloads, reduce or eliminate
`linger.ms` so messages are sent promptly rather than waiting for a
batch to fill. For throughput-sensitive, high-volume workloads, increase
`linger.ms` and `batch.size` together so batches meaningfully fill before
being sent, improving broker-side efficiency and overall throughput at
the cost of some added per-message latency -- this tradeoff should be a
deliberate choice matched to the specific topic/workload's actual
requirements, not a single global default applied to every producer.
If compression overhead is the bottleneck, choose a lighter compression
algorithm (or none, if network isn't the constraint) appropriate to the
producer's available CPU headroom.

## Pitfalls

Don't apply one producer configuration profile uniformly across every
topic/use case in an organization -- latency-sensitive and throughput-
sensitive workloads genuinely need different tuning, and a one-size-fits
-all default optimized for one will hurt the other. Also don't tune
purely by trial and error without actually measuring where latency is
spent (queue time vs. network vs. broker) -- the fix differs
substantially depending on which stage actually dominates.

## Verify

After retuning, measure actual achieved batch sizes and end-to-end
latency under realistic load and confirm they match the intended
tradeoff (lower latency with acceptable throughput for latency-sensitive
workloads, or higher throughput with acceptable latency for throughput-
sensitive ones). Load-test at the workload's actual peak volume to
confirm the tuning holds up under real conditions, not just steady
low-volume testing.
