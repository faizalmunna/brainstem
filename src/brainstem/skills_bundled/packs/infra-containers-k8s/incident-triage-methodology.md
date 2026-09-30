---
name: incident-triage-methodology
description: Triage a production incident systematically (scope, mitigate, then root-cause) instead of jumping straight to root-cause investigation while the system is still degraded.
triggers: ["production incident", "site is down", "on call incident", "outage triage", "how to handle production incident", "service degraded"]
permissions: ["READ"]
---

## Symptom
A production incident is in progress (elevated errors, an outage, severe
latency) and the response is disorganized -- multiple people
investigating without coordination, root-cause analysis happening before
user impact is mitigated, or mitigation attempted without first
understanding the actual scope of impact.

## Likely causes
This is a process/methodology skill, not a single-cause bug -- the
recurring failure mode is **treating incident response as "find and fix
the bug" instead of "stop the bleeding, then find and fix the bug"**,
which are different priorities under time pressure.

## Diagnose
Establish scope before anything else:
1. **What's actually broken, for whom, since when** -- specific error
   rate/latency numbers from monitoring, not just "it's down"; which
   user segments, regions, or features are affected versus unaffected.
2. **What changed recently** -- deploys, config changes, infrastructure
   changes, or external dependency status in the window before symptoms
   started; this is the highest-value early signal, often available
   faster than reading application logs line by line.
3. **Whether the trend is worsening, stable, or already recovering** --
   changes what "urgent" means and whether an immediate mitigation is
   needed before investigation.

## Fix
- **Mitigate before you understand everything**: if a recent deploy
  correlates with the incident's start, roll it back first and confirm
  recovery, then investigate why it broke things -- don't spend the
  mitigation window doing root-cause analysis while users are still
  affected. The same applies to a bad config change, a runaway autoscale
  event, or a clearly-failing dependency that can be circuit-broken/
  failed-over.
- Assign clear roles under time pressure: one person coordinating/
  communicating status, one or a few people actively investigating/
  mitigating -- avoid everyone independently poking at the same system,
  which produces conflicting changes and confused signal.
- Communicate status at a regular cadence (even "still investigating, no
  update" on a timer) to stakeholders, rather than going silent until
  fully resolved -- reduces duplicate "what's going on" interruptions to
  the people actively working the incident.
- Only after impact is mitigated (error rate/latency back to normal),
  move to full root-cause analysis -- with the pressure off, this can be
  done thoroughly rather than rushed.
- Write up what happened, why, what stopped it, and what will prevent
  recurrence (a postmortem) while details are fresh, regardless of how
  the incident was resolved.

## Pitfalls
- Rolling back or mitigating without recording *what* was rolled back and
  why can leave the team without a clear path back to investigating root
  cause later, or without a clear "known good" state to redeploy toward
  once the fix is ready.
- Treating every incident as requiring the same heavyweight process
  (multiple roles, formal comms cadence) even when it's small/contained
  wastes time relative to its actual severity -- calibrate process weight
  to actual impact/scope established during initial triage.
- A blameless-postmortem process that's actually used to assign blame
  (even implicitly) makes people less willing to be transparent about
  what happened during the next incident -- keep the postmortem focused
  on systems/process, not individual fault.

## Verify
Confirm mitigation actually worked using the same metric that indicated
the incident (error rate, latency, availability) returning to baseline
for a sustained period, not just a single good-looking data point,
before declaring the incident resolved and moving fully into
root-cause/postmortem mode.
