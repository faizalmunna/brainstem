---
name: heap-grows-steadily-in-garbage-collected-runtime
description: A process running on a garbage-collected runtime shows steadily increasing heap usage over time despite the garbage collector running normally, eventually leading to out-of-memory crashes or restarts.
triggers: ["memory leak garbage collected language", "heap growing steadily gc running", "java memory leak despite gc", "nodejs memory growing over time"]
permissions: ["READ"]
---

## Symptom

A long-running process (a Java, .NET, Node.js, Python, or similar
garbage-collected application) shows heap memory usage that grows
steadily over hours or days despite the garbage collector running
normally and reclaiming what it can -- eventually leading to
out-of-memory errors or forced restarts, and the growth doesn't
correlate with a proportional increase in actual traffic/workload.

## Likely causes

- **Objects are unintentionally retained by a long-lived reference**
  (a static collection, a cache with no eviction policy, a listener/
  callback registered but never unregistered) that the garbage collector
  correctly treats as still "reachable" and therefore never reclaims,
  even though the application logically no longer needs them.
- **A cache grows without bound** because no size limit or TTL-based
  eviction was implemented, so every new cached entry adds to memory
  without anything ever being removed.
- **Event listeners or callbacks are registered on every request/
  operation but never cleaned up** (a common pattern in event-driven
  code), accumulating a growing number of dead-but-still-referenced
  listener objects over time.
- **A closure or lambda captures more state than intended** (capturing
  an entire enclosing object/scope rather than just the specific field
  actually needed), keeping that larger scope alive for as long as the
  closure itself is referenced, which can be much longer than expected.

## Diagnose

1. Take heap snapshots at two points in time under similar load
   conditions (e.g. an hour apart during steady traffic) and diff them
   using the runtime's heap analysis tooling to identify which object
   types are growing in count.
2. For the growing object type(s), trace the reference chain (the "GC
   roots" path) keeping them alive, using the heap analyzer's dominator
   tree or reference graph view, to identify exactly what's holding onto
   them.
3. Correlate the growth rate against specific application activity
   (a specific endpoint being called, a specific background job running)
   to narrow down which code path is responsible.
4. Check any caches, static collections, or global registries in the
   codebase for whether they have bounded size/eviction, or grow
   unbounded by design or oversight.

## Fix

Add explicit bounds (a maximum size, a TTL-based eviction policy) to any
cache or collection identified as growing unbounded. Ensure event
listeners/callbacks are explicitly unregistered when no longer needed
(paired registration/deregistration, or using a mechanism like weak
references where the language/runtime supports it for exactly this
purpose). Narrow closures to capture only the specific fields they
actually need rather than an entire enclosing scope, where the language
allows explicit capture control. For genuinely necessary long-lived
caches, use a well-tested caching library with built-in eviction rather
than a hand-rolled unbounded map.

## Pitfalls

Don't respond to a memory leak by simply increasing heap size/restarting
the process more frequently as a permanent workaround -- that delays
the OOM crash without fixing the underlying unbounded growth, and the
same leak will eventually catch up to a larger heap too, just more
slowly.

## Verify

After the fix, run the same before/after heap snapshot comparison under
sustained load over an extended period and confirm heap usage stabilizes
(reaches a steady state) rather than continuing to grow. Confirm the
previously-identified growing object type's count no longer increases
unboundedly under the same test conditions.
