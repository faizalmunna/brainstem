---
name: k8s-resource-limits-tuning
description: Set Kubernetes CPU/memory requests and limits based on actual usage instead of guesses, avoiding both OOMKills from too-low limits and poor scheduling density from too-high requests.
triggers: ["kubernetes resource limits", "how to set cpu memory requests", "pod evicted", "cpu throttling kubernetes", "oomkilled", "kubernetes requests vs limits"]
permissions: ["READ"]
---

## Symptom
Either: pods get OOMKilled or throttled under normal load because
requests/limits were set too low (often copy-pasted defaults or a guess),
or nodes run at low actual utilization despite appearing "full" because
requests were set too high, wasting cluster capacity and increasing cost.

## Likely causes
1. **Requests/limits set once from a guess and never revisited** as the
   application's real resource usage changed with traffic growth or code
   changes.
2. **No distinction made between request and limit**, or both set to the
   same value without understanding what each controls: `requests` is
   what the scheduler reserves and uses for bin-packing decisions;
   `limits` is the hard ceiling the container can't exceed (throttled for
   CPU, killed for memory).
3. **CPU limit set too low relative to actual burst needs**, causing CPU
   throttling under load spikes even though average usage looks fine --
   CPU throttling doesn't kill the pod but silently degrades latency/
   throughput, which is easy to miss without specifically monitoring for
   it.
4. **Memory limit set too low relative to actual peak usage** (including
   startup/warm-up memory spikes that exceed steady-state usage),
   causing OOMKills that look like random crashes rather than a sizing
   issue (see `k8s-pod-crashloopbackoff`'s OOMKilled case).

## Diagnose
- Pull actual historical CPU/memory usage for the workload (from
  `kubectl top`, or better, a metrics system with historical data --
  Prometheus/Grafana, cloud provider metrics) across a representative
  time window that includes peak load, not just idle/average.
- Check current `requests`/`limits` against that real usage data: is the
  memory limit close to or below observed peak usage? Is the CPU limit
  below what's needed during load spikes?
- Check for CPU throttling specifically via the container runtime's
  `cpu.stat` (`nr_throttled`/`throttled_time`) or a metrics dashboard
  surfacing it -- this is easy to miss because it doesn't crash the pod,
  it just makes it slower.

## Fix
- Set `requests` close to typical/steady-state usage (so the scheduler
  packs nodes efficiently and reserves what's actually needed) and
  `limits` high enough to cover realistic peak usage plus headroom, based
  on measured data, not a round-number guess.
- For memory specifically, size the limit above observed peak (including
  startup spikes) with meaningful headroom, since exceeding it kills the
  container immediately with no graceful degradation.
- For CPU specifically, consider whether a hard limit is even the right
  choice for a latency-sensitive workload -- CPU limits cause throttling,
  not OOM-style kills, so a workload with bursty needs may benefit from a
  higher limit (or no limit, with reliance on requests plus node-level
  capacity planning) rather than a tight cap that throttles during
  legitimate bursts.
- Re-tune periodically as the application's real usage changes (after
  significant traffic growth, after a major dependency upgrade, after a
  performance optimization) rather than treating the initial values as
  permanent.

## Pitfalls
- Setting `requests` far above actual typical usage "to be safe" reduces
  effective cluster density (fewer pods fit per node) and increases
  infrastructure cost without improving reliability, since `requests`
  don't prevent bursts above them the way `limits` cap usage.
- Removing memory limits entirely to "stop OOMKills" just moves the
  failure mode to the node level (a pod with no limit can consume enough
  memory to trigger node-level memory pressure, potentially affecting
  other pods on the same node) rather than fixing the sizing.
- Tuning based on a single snapshot (`kubectl top` at one moment) instead
  of a representative time window can miss periodic peaks (end-of-day
  batch jobs, traffic spikes) that only show up in historical data.

## Verify
After adjusting, monitor the workload through at least one full cycle of
its typical peak-load pattern and confirm no OOMKills occurred and CPU
throttling metrics dropped to an acceptable level, while checking node-
level utilization didn't regress from over-provisioned requests.
