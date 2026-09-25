---
name: memory-fragmentation-not-a-leak-but-looks-like-one
description: A process's memory usage appears to grow steadily like a leak, but the actual cause is memory fragmentation from allocation patterns, not objects being unintentionally retained.
triggers: ["memory looks like leak but is fragmentation", "process memory not returned to os", "allocator fragmentation mistaken for leak", "memory usage high but no leaked objects found"]
permissions: ["READ"]
---

## Symptom

A process's reported memory usage (as seen by the OS, or by
runtime-level memory metrics) grows steadily over time in a pattern that
looks exactly like a leak -- but a heap analysis specifically looking for
unintentionally-retained objects finds nothing wrong: object counts and
their reachability all look correct, and logical "live" memory usage
stays roughly constant even as total reported memory keeps climbing.

## Likely causes

- **The memory allocator (the runtime's or the OS's) doesn't return freed
  memory back to the OS**, instead keeping it reserved for future
  allocations within the process (a common, often-correct optimization),
  so total process memory as seen externally never shrinks even though
  internally-tracked "used" memory is stable or fluctuating normally.
- **Allocation patterns with highly variable object sizes fragment the
  heap** into many small free blocks that can satisfy some allocation
  sizes but not others, forcing the allocator to request more memory
  from the OS for a large allocation even though total free space (if
  contiguous) would have been sufficient.
- **A generational or specific garbage collection strategy** promotes
  objects to an older generation that's collected less frequently, so
  memory that's actually reclaimable takes longer to be collected than
  an outside observer watching short time windows would expect, looking
  like a slow leak rather than a normal collection delay.
- **Multiple threads/allocation arenas each maintain their own memory
  pools** (common in some allocators for reduced lock contention), and
  memory freed by one thread's arena isn't necessarily available to
  satisfy allocations from a different thread's arena, inflating total
  reported usage beyond what a single unified view would show.

## Diagnose

1. Distinguish "logical live memory" (what the runtime's own heap
   analysis reports as actually reachable/used) from "process resident
   memory" (what the OS reports) -- a genuine leak shows both growing
   together, while fragmentation/allocator behavior shows OS-reported
   memory growing while logical live memory stays flat or grows much
   more slowly.
2. Check the runtime/allocator's own fragmentation-related metrics or
   debug output, if available, to directly measure fragmentation rather
   than inferring it.
3. Correlate memory growth with the specific allocation size variability
   in the workload -- highly variable allocation sizes are a strong
   signal for fragmentation as the mechanism.
4. Check garbage collection generation statistics (for GC'd runtimes) to
   rule out simply a longer-than-expected collection delay for
   older-generation objects.

## Fix

If the allocator's behavior (not returning memory to the OS) is
confirmed as expected/benign, this may not require a "fix" at all beyond
correctly interpreting the metric -- document this so future
investigations don't repeat the same false-leak alarm. Where genuine
fragmentation is confirmed as the cause and is operationally problematic
(memory usage growing enough to threaten OOM), consider reducing
allocation size variability (bucketing/padding similarly-purposed
allocations to standard sizes) or using an allocator/runtime
configuration better suited to the workload's actual allocation pattern.
For GC-related generational delay, tuning collection frequency for the
older generation may help if the delay is genuinely operationally
significant, weighed against the throughput cost of more frequent
collection.

## Pitfalls

Don't spend significant engineering time hunting for a "leak" using
heap-reachability analysis when the actual signal (OS-reported memory)
diverges from logical live memory -- correctly diagnosing fragmentation
versus a genuine leak first saves substantial wasted investigation
effort.

## Verify

Confirm the distinction holds by monitoring both logical live memory and
OS-reported process memory together over an extended period -- a
genuine leak shows both growing in tandem, while fragmentation/allocator
behavior shows a persistent gap between the two that doesn't
continuously widen once explained (or does need addressing if it does).
