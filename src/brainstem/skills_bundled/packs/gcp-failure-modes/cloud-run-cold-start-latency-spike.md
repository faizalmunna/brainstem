---
name: cloud-run-cold-start-latency-spike
description: A Cloud Run service shows occasional very high latency spikes for individual requests because a new container instance had to cold-start to handle them.
triggers: ["cloud run cold start latency", "google cloud run slow first request", "cloud run scaling latency spike", "cloud run min instances needed"]
permissions: ["READ"]
---

## Symptom

A Cloud Run service's latency metrics show mostly fast, consistent
response times, but a small percentage of requests take dramatically
longer -- often correlating with traffic spikes, deploys, or periods of
low traffic followed by a burst -- rather than being uniformly
distributed.

## Likely causes

- **No minimum instance count is configured**, so Cloud Run scales the
  service to zero during idle periods, and the next request after an idle
  period pays the full cost of starting a new container (pulling the
  image, initializing the runtime, running application startup code).
- **Application startup work is heavy** (loading a large ML model,
  establishing multiple connections, running migrations at boot) and adds
  significantly to cold-start time on top of the base container startup
  cost.
- **A traffic burst exceeds current instance count faster than new
  instances can start**, so even with some warm instances already
  running, the burst's excess requests queue behind newly starting
  instances rather than being served immediately.
- **The container image is large**, increasing image-pull time as part of
  cold start, especially if a new revision was just deployed and no
  instances have that specific image cached yet.

## Diagnose

1. Check Cloud Run's built-in metrics for "container instance count" and
   "startup latency" alongside request latency, and correlate spikes in
   request latency with periods where instance count was actually scaling
   up from zero or from a low baseline.
2. Check the configured minimum instance count (`--min-instances`) for
   the service -- a value of 0 confirms cold starts are structurally
   possible during idle periods.
3. Profile the application's actual startup sequence (time from container
   start to serving the first request) to quantify how much of cold-start
   latency is the platform's container startup versus the application's
   own initialization code.
4. Check container image size and whether a recent deploy introduced a
   larger image or new heavy dependencies.

## Fix

Set a minimum instance count greater than zero for latency-sensitive
services, accepting the cost tradeoff of keeping instances warm even
during idle periods, sized to the traffic pattern's actual idle-to-burst
transition needs. Reduce application startup time where possible (lazy-
load non-critical dependencies, defer heavy initialization until first
actual use rather than blocking service readiness, minimize container
image size). For traffic bursts specifically, tune concurrency settings
(how many requests one instance handles simultaneously) so existing warm
instances can absorb more of a burst before needing to scale out to new
cold instances at all.

## Pitfalls

Don't set minimum instances so high that idle cost becomes
disproportionate to actual traffic needs -- balance the latency benefit
against the always-on cost, and consider whether the specific endpoints
experiencing cold starts are actually latency-sensitive enough to justify
it (a background/batch endpoint may not need the same treatment as a
user-facing API). Also don't assume increasing minimum instances alone
fully solves burst-related scaling latency if the burst size regularly
exceeds even the configured minimum -- combine with concurrency tuning
and realistic max-instance headroom.

## Verify

After configuring minimum instances, monitor cold-start-attributable
latency spikes over a subsequent period covering typical idle-to-burst
transitions and confirm they're reduced to an acceptable rate. Load-test
a simulated burst scenario and confirm the combination of minimum
instances and concurrency settings keeps the majority of requests within
acceptable latency during the transition.
