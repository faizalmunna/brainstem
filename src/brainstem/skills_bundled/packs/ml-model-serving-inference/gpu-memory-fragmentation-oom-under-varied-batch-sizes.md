---
name: gpu-memory-fragmentation-oom-under-varied-batch-sizes
description: A model serving process runs out of GPU memory intermittently under production traffic despite having enough total memory, because varying batch/input sizes fragment GPU memory over time.
triggers: ["gpu out of memory intermittent", "cuda oom despite available memory", "gpu memory fragmentation inference", "model server crashes oom under variable load"]
permissions: ["READ"]
---

## Symptom

A model serving process crashes or throws out-of-memory errors on the
GPU intermittently during normal production operation, despite total GPU
memory usage (as reported by monitoring) appearing to have headroom --
the failures correlate with variable request patterns (different batch
sizes, different input sequence lengths) rather than sustained high
memory usage.

## Likely causes

- **GPU memory fragmentation from repeatedly allocating and freeing
  differently-sized tensors** (from varying batch sizes or input
  lengths) leaves memory in small, non-contiguous free blocks that can't
  satisfy a subsequent large allocation, even though the sum of free
  memory would be enough if it were contiguous.
- **The memory allocator's caching behavior** (many deep learning
  frameworks cache freed GPU memory for reuse rather than returning it
  to the OS immediately) interacts poorly with highly variable allocation
  sizes, since a cached block sized for one shape can't be reused for a
  differently-shaped request without a fresh allocation.
- **A memory usage spike from an unusually large batch or long sequence
  request** pushes usage close to the limit, and the specific allocation
  pattern of that spike leaves fragmented free space behind even after
  the spike's memory is released.
- **No maximum batch size or input length limit is enforced**, so an
  unusually large, legitimate-looking request can trigger an allocation
  large enough to fail even with otherwise reasonable memory management.

## Diagnose

1. Reproduce the OOM in a controlled test by sending a sequence of
   varying batch-size/input-length requests similar to the production
   pattern that preceded a real failure, to confirm fragmentation as the
   mechanism rather than sustained high usage.
2. Use the framework's GPU memory profiling tools to inspect actual
   memory layout (allocated vs. cached vs. free, and fragmentation
   metrics if available) at the point of failure.
3. Check whether a maximum batch size/input length limit is currently
   enforced, and what the actual observed range of request sizes looks
   like in production traffic.
4. Check the framework's memory allocator configuration for any
   fragmentation-mitigation options (a different allocator backend,
   periodic cache clearing) that aren't currently enabled.

## Fix

Enforce explicit maximum batch size and input length limits sized to
what the GPU can reliably handle with headroom, rejecting or splitting
requests that would exceed them rather than allowing unbounded variation
to drive fragmentation. Where the framework supports it, configure the
memory allocator to reduce fragmentation (a different allocation
strategy, periodic explicit cache clearing during low-traffic windows).
Consider bucketing requests into a small number of standard batch/
sequence-length buckets (padding to the nearest bucket size) rather than
allowing fully arbitrary sizes, which reduces the variety of allocation
shapes the allocator has to manage and directly reduces fragmentation
risk.

## Pitfalls

Don't respond to intermittent OOM by simply provisioning a GPU with more
total memory -- if the root cause is fragmentation, more total memory
delays but doesn't eliminate the problem, since fragmentation scales with
allocation variety and traffic volume, not just being bounded by a fixed
headroom multiplier.

## Verify

Replay the production traffic pattern that previously caused OOM (or a
synthetic equivalent with the same variability) against the fixed
configuration and confirm no OOM occurs over an extended test run.
Monitor GPU memory fragmentation metrics (if available) in production
after the fix and confirm they stay within a stable, bounded range
rather than trending toward exhaustion over time.
