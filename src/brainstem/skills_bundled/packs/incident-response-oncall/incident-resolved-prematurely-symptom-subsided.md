---
name: incident-resolved-prematurely-symptom-subsided
description: An incident is declared resolved because the symptom subsided on its own without confirming the root cause was actually fixed, and it recurs.
triggers: ["incident closed too early", "the problem came back after we resolved it", "error rate went back to normal so we closed the incident", "declared resolved but recurred", "premature incident resolution"]
permissions: ["READ"]
---

## Symptom
An incident's key metric (error rate, latency, queue depth) returns to
normal, everyone breathes a sigh of relief, the incident is marked
resolved, and the channel goes quiet. Hours or days later, the identical
symptom returns -- sometimes worse -- because whatever actually caused
the first occurrence was never identified or fixed; the metric recovering
was coincidental (traffic dropped, a retry loop happened to succeed, an
upstream dependency happened to recover on its own) rather than caused by
any action the team took.

## Likely causes
- **Recovery was correlated with an action but never confirmed as
  caused by it** -- a service was restarted around the same time the
  metric recovered, and the team assumed the restart fixed it without
  checking whether the timing was coincidental (e.g. traffic naturally
  dropping, an external dependency recovering independently).
- **The incident's mitigation addressed the symptom, not the mechanism**
  -- scaling up instances to work around a memory leak makes the metric
  look fine while the leak itself is still there and will reappear at the
  next capacity boundary.
- **Pressure to close incidents quickly** (a status page needs to update,
  people want to stop being paged, an on-call shift is ending) creates
  incentive to declare victory at the first good-looking data point
  rather than watching for a sustained return to baseline plus an
  understood mechanism.
- **No explicit resolution criteria were defined at incident start** --
  without agreeing in advance what "resolved" requires (root cause
  understood, fix verified, metric stable for N minutes), the bar
  defaults to "does it look okay right now."

## Diagnose
1. Check the incident record for whether a specific causal mechanism was
   identified and confirmed (e.g. "we found and reverted the exact commit
   that introduced the leak, and reproduced the leak in staging to
   confirm") versus just "metric returned to normal."
2. Check the timing precision between the claimed fix action and metric
   recovery -- was recovery immediate and step-like right after the
   action, or gradual/already-in-progress before the action, suggesting
   an unrelated cause (traffic pattern, upstream recovery)?
3. Look for whether the mitigation was capacity/workaround-shaped
   (restart, scale up, clear a queue) versus mechanism-shaped (revert a
   specific change, fix a specific bug) -- workaround-shaped mitigations
   without a follow-up root-cause fix are the highest-risk case for
   recurrence.
4. Check whether recurrence has already happened for this exact symptom
   in the incident history -- a repeat of the same signature (same
   service, same metric, same rough time-of-day pattern) is direct
   evidence the first resolution was symptomatic, not causal.

## Fix
Define resolution criteria before or during the incident, not
retroactively at the moment it looks better: require (1) a stated,
specific causal mechanism, not just a correlated action, (2) the metric
sustained at baseline for a defined window appropriate to the failure
mode (minutes for a request-level issue, longer for something like a slow
memory leak or gradual resource exhaustion), and (3) a follow-up task to
address the mechanism if the immediate action was only a workaround
(restarted, scaled, failed over) rather than a genuine fix. When the
mitigation was a workaround, explicitly mark the incident as "mitigated"
rather than "resolved" until the underlying mechanism is actually
addressed, and keep elevated monitoring on the affected system for a
defined period afterward specifically watching for recurrence.

## Pitfalls
Don't let "we need to keep watching" become an indefinite, un-owned
vigil that quietly gets forgotten the same way action items do -- attach
a specific end date/condition to the elevated monitoring, and a specific
owner for the root-cause follow-up. Also don't require full root-cause
certainty before ever closing an incident -- for genuinely low-severity,
low-recurrence-risk issues that would cost more to fully root-cause than
they're worth, it's fine to consciously accept the risk and close, but
that should be an explicit decision recorded as such, not a default from
not checking.

## Verify
For any incident closed as "resolved" (not just "mitigated"), confirm the
postmortem or ticket states the specific causal mechanism and how it was
verified (a reproduction, a code diff, a config diff), not just "the
metric recovered." Track recurrence of the same symptom signature over
the following weeks; a properly root-caused incident should not
reappear, and if it does, treat that recurrence itself as evidence the
original resolution was premature and feed it back into the fix.
