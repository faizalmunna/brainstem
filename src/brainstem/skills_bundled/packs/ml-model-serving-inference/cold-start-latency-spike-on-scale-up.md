---
name: cold-start-latency-spike-on-scale-up
description: A model serving instance that just scaled up shows dramatically higher inference latency for its first requests because model weights and framework initialization aren't warm yet.
triggers: ["model serving cold start latency", "new inference instance slow first requests", "gpu warm up delay inference", "scaling model server causes latency spike"]
permissions: ["READ"]
---

## Symptom

When a model serving deployment scales up (adding a new instance to
handle increased traffic), the new instance's first several requests
show dramatically higher latency than the already-running instances --
sometimes high enough to cause timeouts -- before settling into normal
performance.

## Likely causes

- **Model weights need to be loaded from disk/network storage into
  memory (and onto GPU, if applicable) when the instance starts**, and
  for large models this loading time alone can take significant time
  before the instance can serve any request at reasonable speed.
- **The inference framework/runtime needs to perform its own
  initialization** (CUDA context setup, kernel compilation/JIT
  warmup for the specific input shapes it first encounters, graph
  optimization) that adds latency to the very first requests
  specifically, distinct from ongoing steady-state latency.
- **No warm-up requests are sent to a new instance before it's added to
  the load balancer's active pool**, so real user traffic is the first
  thing exercising the cold instance's initialization path.
- **Autoscaling reacts to load with a lag** (detecting the need to scale,
  then the time to actually start a new instance and load the model),
  so by the time the new instance is ready, it may immediately receive a
  burst of traffic that was queuing while waiting for capacity.

## Diagnose

1. Measure and separate model-loading time from framework
   initialization time from actual first-inference time, to identify
   which specific stage dominates cold-start latency.
2. Check whether any warm-up mechanism exists (a synthetic request sent
   before the instance is added to the load balancer pool) or whether
   real traffic is the first exercise of the cold path.
3. Check autoscaling configuration for trigger thresholds and instance
   startup time, to understand the actual lag between load increase and
   new capacity becoming genuinely ready.
4. Profile whether specific input shapes/batch sizes trigger additional
   JIT compilation on first encounter (common in frameworks that compile
   per-shape), which could explain latency spikes correlated with
   specific request patterns rather than just instance age.

## Fix

Implement a warm-up step in the instance startup sequence -- send
synthetic requests representative of real traffic (including the range
of input shapes/batch sizes expected) before adding the instance to the
load balancer's active pool, so cold-path initialization happens before
real user traffic hits it. For frameworks with per-shape compilation
overhead, warm up with the actual range of shapes production traffic
uses, not just one example. Tune autoscaling to trigger earlier
(anticipating load rather than purely reacting to it) to give new
instances more lead time to warm up before traffic actually arrives at
them. Consider maintaining a small pool of pre-warmed standby instances
for latency-critical services where cold-start cost is unacceptable even
occasionally.

## Pitfalls

Don't warm up with only a single, simple example request if production
traffic actually varies significantly in input shape/size -- an
insufficient warm-up leaves later, differently-shaped requests still
hitting a partially-cold path. Also don't over-provision standby
capacity to avoid cold starts entirely without weighing the real
infrastructure cost of keeping extra instances warm continuously.

## Verify

Deploy a new instance with the warm-up step in place and measure actual
latency for its first real requests after being added to the pool,
confirming it's now comparable to steady-state latency on already-
running instances rather than showing the previous cold-start spike.
