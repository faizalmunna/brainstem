---
name: no-numeric-target-for-optimization-effort
description: A performance investigation drags on indefinitely because nobody defined how fast is fast enough before starting to optimize.
triggers: ["how do we know when we're done optimizing", "when is it fast enough", "we keep optimizing but don't know if it matters", "no performance target defined for this project"]
permissions: ["READ"]
---

## Symptom

A performance effort starts from a vague complaint ("this feels slow,"
"users are complaining about load times") and continues for weeks, with
each optimization justified by "it's faster than before," but there's no
point at which anyone can say the work is done, whether the remaining
gap matters, or whether a given optimization's complexity cost was
worth what it bought. Effort keeps being spent past the point of
diminishing, or even negative, business value.

## Likely causes

- **No specific numeric target was set at the start** (e.g., "p95 API
  latency under 200ms" or "page interactive within 2.5s") -- without one,
  every improvement looks like progress and there's no defined stopping
  point, so the investigation is scoped by available time/patience
  rather than by a requirement.
- **The target that exists is vague or non-actionable** ("make it fast,"
  "improve performance") rather than tied to a specific metric,
  percentile, and user-facing threshold that can be measured and
  checked against.
- **No cost/benefit framing for individual optimizations** -- a change
  that adds meaningful code complexity, a new caching layer, or a
  maintenance burden is accepted purely because it improves a number,
  without asking whether the improvement is large enough to justify the
  ongoing cost of maintaining it.
- **The target, if it exists, isn't tied to something that actually
  matters to users or the business** (an internal benchmark number
  rather than a user-observable outcome like task completion time,
  conversion rate, or SLA compliance), so hitting it doesn't obviously
  correlate with anything anyone outside the team cares about.

## Diagnose

1. Ask directly: what is the specific numeric target, in what metric
   (p50/p95/p99 latency, throughput, time-to-interactive), measured
   where (client, server, specific endpoint)? If nobody can answer this
   precisely, that's the actual root cause of the open-ended effort.
2. Check whether an existing target is derived from something concrete
   (an SLA, a competitor benchmark, a user research finding about
   perceived slowness, a documented business requirement) versus being
   an arbitrary round number picked without justification.
3. For each optimization under consideration or already shipped,
   check whether its expected/measured gain and its added complexity
   (new dependencies, cache invalidation surface, code readability cost)
   were both stated together anywhere (a PR description, a design doc) --
   if only the gain was ever discussed, the cost side was never actually
   weighed.
4. Check whether the current numeric state (actual measured p95, etc.)
   has been compared against the target explicitly and recently, rather
   than the team operating purely on "faster is better" momentum.

## Fix

Before further optimization work, establish an explicit, specific
numeric target tied to a real requirement: an SLA, a documented UX
research threshold (e.g., a well-known interactivity budget), or a
concrete business metric with a stated relationship to latency
(conversion drop-off past a certain load time). Track current
measurement against that target continuously (a dashboard, not a
one-time check), and treat further optimization as unnecessary, or at
least lower priority, once the target is met -- reallocate effort
elsewhere rather than continuing to chase incremental gains with no
defined value. For each candidate optimization, require a stated
expected gain and complexity cost before implementing it, and reject
optimizations whose complexity cost is disproportionate to a marginal
gain past the target.

## Pitfalls

Don't set a target that's technically arbitrary (a round number with no
tie to user experience or a real SLA) just to have *a* number -- an
unjustified target produces the same wasted-effort outcome if it's set
too aggressively (over-optimizing past the point anyone benefits) or
too loosely (stopping before a real user-facing problem is fixed). Also
avoid treating "we hit the target" as permanent -- targets should be
revisited when traffic, data volume, or user expectations shift
materially, not abandoned as a one-time exercise.

## Verify

Confirm a written, specific target exists (metric, percentile,
threshold, and the reasoning tying it to a real requirement), that it's
visible on the same dashboard as the live measurement, and that the
most recent optimization decision in the project can be traced to
either "moves us toward the unmet target" or "explicitly deprioritized
because the target is already met" -- not to unattributed intuition
about what "should" be faster.
