---
name: gke-pod-oomkilled-despite-low-average-usage
description: A GKE pod is repeatedly OOMKilled even though its average memory usage graph looks well under the configured limit, because a short usage spike between metric samples exceeded it.
triggers: ["gke pod oomkilled low average memory", "kubernetes oom despite low usage graph", "pod restarting oom kubernetes gke", "memory spike between metrics samples"]
permissions: ["READ"]
---

## Symptom

A pod in a GKE cluster is repeatedly killed and restarted with an
`OOMKilled` status, but the memory usage graph in monitoring (sampled at
a typical interval like every 30-60 seconds) shows average usage
comfortably under the configured memory limit, making the restarts seem
to contradict the available metrics.

## Likely causes

- **A short-lived memory spike occurs between metric sample points** (a
  burst of allocation during a specific request or batch operation that
  lasts only a few seconds), which the sampling interval is too coarse to
  capture, so the graph shows a smoothed average that hides the actual
  peak that triggered the OOM kill.
- **The memory limit is set based on average/typical usage rather than
  peak usage**, without headroom for legitimate but infrequent spikes
  (a large request payload, a batch job, garbage collection behavior in
  some runtimes that can temporarily increase memory before reclaiming
  it).
- **A memory leak causes usage to climb between pod restarts**, but the
  restart itself (triggered by the OOM kill) resets memory to a low
  baseline before the next sample, making a graph sampled at the wrong
  cadence look like usage never got high, when in fact it climbed and
  reset repeatedly within each sampling window.
- **cgroup memory accounting includes page cache/buffers in ways that
  differ from what the application-level or coarse monitoring reports**,
  so the actual OOM-triggering memory pressure as seen by the kernel
  doesn't match what a higher-level, less granular metric shows.

## Diagnose

1. Check the pod's actual OOM kill events and timestamps (via `kubectl
   describe pod` or GKE's own event/audit logs) and correlate precisely
   with what the application was doing at that exact moment (a specific
   request, a scheduled job) rather than relying on a coarse average
   graph.
2. Increase metric sampling frequency temporarily (or use a
   finer-grained profiling tool) around a reproducible trigger to
   actually capture the short-lived spike the coarse graph misses.
3. Check the container's actual memory limit configuration against the
   process's peak (not average) memory usage under a realistic worst-case
   load test.
4. If a slow leak is suspected, look at memory trend within a single pod
   lifetime (from its own start time to its OOM kill time), not across
   the fleet average, to see if there's a climbing pattern reset by each
   restart.

## Fix

Set memory limits based on measured peak usage under realistic worst-case
load (including legitimate spikes), not average usage from a coarse
graph, with reasonable headroom. For a confirmed short-lived, legitimate
spike (not a leak), consider whether the spike itself can be reduced
(streaming a large payload instead of buffering it fully in memory,
processing a batch in smaller chunks) rather than only raising the
limit. For a confirmed slow leak, fix the actual leak in application code
rather than treating a higher memory limit or more frequent restarts as
an acceptable long-term workaround.

## Pitfalls

Don't raise the memory limit dramatically without understanding whether
the root cause is a legitimate rare spike (where a moderate limit
increase with headroom is reasonable) or a genuine leak (where a limit
increase just delays the inevitable OOM kill to a later point, wasting
resources in the meantime). Also don't rely solely on coarse default
monitoring dashboards to declare a memory issue "not real" just because
the graph looks fine -- the coarse sampling itself can be the reason the
issue is invisible.

## Verify

After adjusting the memory limit (and/or fixing the underlying cause of
a spike or leak), monitor OOM kill events specifically (not just the
usage graph) over a period covering the original triggering condition,
and confirm zero further OOM kills under the same realistic load pattern
that previously caused them.
