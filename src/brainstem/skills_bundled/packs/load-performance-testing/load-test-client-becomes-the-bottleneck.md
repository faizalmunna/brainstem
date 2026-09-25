---
name: load-test-client-becomes-the-bottleneck
description: A load test reports the system handles the target throughput, but production falls over at the same load, because the load-generating client itself was the actual bottleneck.
triggers: ["load test passed but production failed", "load generator maxed out not server", "k6 client cpu bound", "load test results not matching production"]
permissions: ["READ"]
---

## Symptom

A load test (k6, Locust, JMeter, Gatling) reports the system under test
handling the target requests-per-second with acceptable latency, giving
confidence to launch, but production falls over at that same real-world
load -- with server-side metrics during the load test showing the server
was never actually near its own resource limits.

## Likely causes

- **The load-generating machine/process itself hit a resource limit**
  (CPU, network bandwidth, open file descriptors, thread pool size)
  before the target system did, capping the actual achieved load well
  below what was intended, while the test tool reported "success" against
  its lower, actual achieved rate rather than the originally intended one.
- **A single load-generator instance's own network stack** (ephemeral
  port exhaustion, TCP connection reuse limits) throttled how many
  concurrent connections it could actually open, independent of the
  target server's capacity.
- **The load-testing tool's own scripting/correlation overhead** (client-
  side response parsing, complex assertions per request) consumed enough
  CPU on the generator that it couldn't generate requests as fast as
  configured.
- **Load was generated from a single machine/region** with different
  network characteristics (lower latency, higher bandwidth) than real
  users, understating real-world variance the actual production traffic
  would exhibit.

## Diagnose

1. Check the load-generating machine's own resource utilization (CPU,
   memory, network) during the test run, not just the target system's --
   most load-testing tools report this, or it can be monitored
   separately with standard OS tools.
2. Compare the *intended* load configuration (requests/sec, concurrent
   users configured) against the *actually achieved* load reported by the
   tool -- a gap between the two is a strong signal the generator itself
   couldn't keep up.
3. Check the load-testing tool's own documentation/known limits for
   single-instance throughput ceilings, and compare against what was
   attempted.
4. If using a single generator instance, try distributing the load
   across multiple generator instances/machines and see if the achieved
   throughput increases -- if it does, the single generator was capped.

## Fix

Verify the load generator has meaningfully more resource headroom than
the throughput being tested -- monitor its own CPU/network/connection
usage during every load test run as a first-class metric, not an
afterthought. For load beyond what a single machine can realistically
generate, distribute the load across multiple generator instances (most
modern tools like k6 and Locust support distributed/cloud execution
modes for exactly this reason) rather than pushing a single instance past
its own limits. Where possible, generate load from multiple geographic
regions to better approximate real user network diversity, especially for
systems with a globally distributed user base.

## Pitfalls

Don't assume a more expensive/larger generator machine alone fixes this
without also checking OS-level limits (file descriptor limits, ephemeral
port ranges, TCP tuning) that can cap a single instance's connection
count regardless of raw CPU/memory headroom. Also don't over-correct by
assuming every load test needs a distributed generator setup -- for
genuinely modest target loads, confirm the bottleneck exists first before
adding the operational complexity of distributed load generation.

## Verify

Re-run the load test while explicitly monitoring the generator's own
resource usage and confirm it stays comfortably below saturation at the
target load; confirm the *achieved* throughput matches the *intended*
configured throughput, not just that the test tool exited without error.
Cross-reference server-side metrics (CPU, latency, error rate) during the
corrected test run to confirm the target system is now actually the
limiting factor being measured, not the generator.
