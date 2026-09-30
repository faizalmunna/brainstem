---
name: load-test-think-time-unrealistic-traffic-shape
description: A load test's pacing between simulated user actions doesn't match real user behavior, producing an unrealistically smooth or unrealistically bursty traffic pattern that hides how the system actually behaves under real load.
triggers: ["load test traffic pattern unrealistic", "think time misconfigured", "load test too smooth compared to real traffic", "burst traffic not simulated"]
permissions: ["READ"]
---

## Symptom

A load test's throughput graph looks like a perfectly smooth, constant
rate of requests, but production traffic graphs for the same nominal
average load show clear bursts and lulls -- and the system handles the
smooth synthetic load fine while struggling during real bursty periods
that have the same or lower average rate.

## Likely causes

- **No think-time (pacing delay between simulated user actions) was
  configured, or it was set to a fixed, uniform value**, producing a
  perfectly even request rate that doesn't reflect how real users
  actually interact with an application in irregular bursts.
- **Virtual users in the test are perfectly synchronized** (all starting
  their next action at the same relative offset), which either smooths
  out load unrealistically or, in some tool configurations, creates
  artificial synchronized bursts that don't reflect independent real
  users acting on their own schedules.
- **The test doesn't model realistic traffic shape events** (a marketing
  email send, a scheduled batch job, a time-zone-driven daily peak) that
  cause genuine bursts in production but have no equivalent in a
  steady-average synthetic test.
- **Average requests-per-second was used as the sole load-test target**
  without considering that the same average can be produced by very
  different underlying distributions (smooth vs. bursty), which can
  stress a system very differently (queueing, autoscaling reaction time)
  even at an identical average rate.

## Diagnose

1. Compare the load test's request-rate time series (zoomed in to
   second-by-second or sub-second granularity, not just the test's
   overall average) against a real production traffic graph for a
   comparable period.
2. Check the load-testing tool's think-time/pacing configuration for
   whether it uses a fixed delay, a randomized range, or a distribution
   modeled on real user behavior data.
3. Check whether virtual users are staggered (randomized start offsets)
   or synchronized in how the test tool ramps and paces them.
4. Identify any known real-world burst-inducing events for this system
   (marketing sends, scheduled jobs, daily/weekly peaks) and check
   whether the load test scenario models anything equivalent.

## Fix

Configure think-time using a randomized distribution (not a fixed value)
that approximates real user behavior, ideally derived from actual
session/analytics data showing real inter-action timing. Stagger virtual
user start times and independent pacing so the aggregate traffic shape
emerges from many independently-paced simulated users rather than a
synchronized, artificially smooth or artificially bursty pattern.
Explicitly design at least one test scenario around a known real burst
event (a traffic spike shape derived from a real past incident or
marketing event) in addition to steady-state average-load testing, since
the two measure genuinely different things.

## Pitfalls

Don't over-randomize think-time to the point the test becomes
non-reproducible run to run in a way that makes regressions hard to
detect -- use a fixed random seed for reproducibility while still
modeling realistic variance in pacing. Also don't assume matching the
*shape* of one specific past traffic pattern guarantees coverage of all
realistic future patterns -- treat burst modeling as an additional,
targeted scenario alongside (not a replacement for) general steady-state
and ramp testing.

## Verify

Compare the corrected load test's request-rate time series against real
production data and confirm the statistical shape (burstiness,
variance) is now meaningfully closer, not just the average rate. Confirm
system behavior differs appropriately between the smooth steady-state
scenario and the deliberately bursty scenario at the same average rate,
demonstrating the test now actually distinguishes between the two rather
than treating them as equivalent.
