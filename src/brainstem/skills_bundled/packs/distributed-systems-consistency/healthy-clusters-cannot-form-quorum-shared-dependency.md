---
name: healthy-clusters-cannot-form-quorum-shared-dependency
description: Two independently healthy, geographically separate deployments cannot reach quorum for a decision because of an unexpected shared dependency neither side anticipated.
triggers: ["quorum failure across regions both sides healthy", "cross-region deployments cant agree despite both being up", "shared dependency broke quorum between independent clusters", "coordination bottleneck between healthy sites"]
permissions: ["READ"]
---

## Symptom

Two (or more) deployments of the same service in different regions or
data centers are each individually healthy -- passing health checks,
serving local traffic fine -- but a decision that requires agreement
across them (a quorum vote, a distributed lock, a leader election
spanning sites) never completes. The system behaves as if it's fully
down for that cross-site decision even though every node involved
reports itself as up, and the on-call response is confusing because
"nothing is failing" from any single site's point of view.

## Likely causes

- **Both sites depend on a single shared coordination resource that
  neither team modeled as a cross-site dependency** -- a shared DNS
  resolver, a single-region message queue, a shared auth/identity
  service, or a third-party API that both deployments call as part of
  their quorum protocol, and that resource is degraded or unreachable
  from one or both sides.
- **The quorum mechanism itself routes through infrastructure that
  isn't actually redundant across the same fault boundary the
  deployments are meant to be independent across** -- e.g. two
  "independent" regional deployments both rely on the same global
  load balancer, the same central metadata service, or the same
  single-region database for coordination state.
- **A capacity or rate limit on the shared dependency is being hit
  only when both sites are simultaneously healthy and both trying to
  use it**, so the bottleneck only manifests under the specific
  condition of both sides being up and attempting to coordinate --
  invisible in single-site testing.
- **Asymmetric network reachability to the shared dependency** (one
  site can reach it, the other can't, due to a firewall rule, peering
  change, or partial outage at a third-party provider) means the two
  sides have differing views of the same resource's health, and
  quorum logic that assumes symmetric reachability breaks.

## Diagnose

1. Map every dependency the quorum/coordination path touches end to
   end for both sites -- not just "is site A up" and "is site B up,"
   but literally every service, DNS lookup, and network hop the
   quorum decision logic invokes, and mark which of those are
   single-instance or single-region.
2. Check the shared dependency's own health/latency/error-rate metrics
   for the exact incident window, independent of either site's health
   dashboards -- the smoking gun is usually a resource that looks
   "fine" on its own dashboard but is degraded specifically for
   cross-region traffic patterns (elevated latency, connection pool
   exhaustion, regional throttling).
3. From each site independently, run a direct reachability/latency
   test against the shared dependency (not through the application)
   to check for asymmetric network issues -- a traceroute or simple
   authenticated request from each region.
4. Check the shared dependency's rate limits, connection quotas, or
   concurrency limits against the combined load both sites generate
   when both attempt coordination simultaneously, versus what either
   site generates alone.
5. Review the incident timeline for whether the quorum failure started
   exactly when both sites became healthy simultaneously (versus one
   site being down) -- that timing signature points strongly at a
   shared-dependency bottleneck rather than either site's own health.

## Fix

Treat cross-site coordination dependencies as first-class
architecture decisions, not incidental plumbing: explicitly diagram
every resource the quorum path touches and classify each as
genuinely redundant across the fault boundary or not. For any shared
dependency that can't reasonably be made redundant (e.g. a specific
third-party API), design the quorum/decision logic to degrade
gracefully when that dependency is unavailable -- falling back to a
documented, tested reduced-availability mode -- rather than treating
its unavailability as an undefined state. Where the shared dependency
is internal infrastructure (DNS, a message queue, a metadata store),
deploy it redundantly per-region with no single point that both sites
must reach, so a regional issue can't silently become a cross-region
coordination outage.

## Pitfalls

Don't stop the investigation once each individual site is confirmed
healthy -- "both sites pass their own health checks" is exactly the
condition that makes this failure mode hard to find, and closing the
incident on that basis without tracing the actual coordination path
guarantees a repeat. Also don't add a shared dependency as a "quick
fix" for coordination (e.g. routing quorum decisions through a single
convenient existing service) without evaluating its capacity under
the specific load pattern of both sites being simultaneously healthy
and coordinating -- that's precisely the untested case.

## Verify

Build a dependency map of the quorum path and confirm, for each
shared resource, there is either genuine per-region redundancy or a
tested degraded-mode fallback. Run a game-day exercise where both
sites are deliberately brought to healthy status simultaneously under
realistic load and the cross-site quorum decision is exercised
end-to-end, watching the previously-bottlenecked shared dependency's
metrics throughout to confirm it no longer saturates.
