---
name: severity-underclassified-delayed-escalation
description: An incident is initially classified at a lower severity than warranted, which delays escalation to the people who could resolve it faster.
triggers: ["incident severity was wrong", "should have been a sev1", "escalated too late", "we underestimated the incident severity", "took too long to page the right team"]
permissions: ["READ"]
---

## Symptom
An incident starts as a Sev3 or Sev4 ("minor," handled by whoever's
already looking at it) and stays that way for an hour or more before
someone realizes the actual customer impact is severe, at which point it
gets re-classified as Sev1 and the right specialists/leadership get
paged -- but by then, meaningful time has been lost that a faster
escalation would have saved. The postmortem timeline shows a visible gap
between "impact began" and "correct people engaged."

## Likely causes
- **Severity was judged from the first available signal (one team's
  dashboard, one error type) rather than actual customer/business
  impact**, which understates scope when the failure cascades across
  services not yet visibly affected.
- **The person who first noticed the issue lacked the context to
  recognize its blast radius** -- e.g. an on-call engineer for service A
  doesn't know that service A's degradation silently breaks checkout for
  the whole site, so they classify it as a local issue.
- **Severity definitions are vague or overlap** ("significant" vs. "major"
  vs. "critical" with no measurable threshold), so classification depends
  on the individual's judgment and risk tolerance rather than an
  objective rule, and cautious engineers under-escalate to avoid "crying
  wolf."
- **Re-classifying upward feels like a socially costly admission of
  having judged wrong initially**, so there's reluctance to page more
  people or notify leadership until the evidence is overwhelming, which
  is itself a symptom of a non-blameless escalation culture.
- **No automatic re-evaluation trigger** -- severity is set once at
  declaration time and nothing prompts anyone to revisit it as new
  information (error rate climbing, more services affected) comes in.

## Diagnose
1. Reconstruct the incident timeline: time impact actually began (from
   metrics, not from when someone noticed), time it was declared, initial
   severity assigned, time of re-classification, and time the right
   people were actually engaged. The gap between "impact began" and
   "right people engaged" is the cost of misclassification.
2. Check the severity rubric being used: does it define severity by
   measurable customer/business impact (revenue-affecting, % of users
   affected, SLO breach) or by vague adjectives left to judgment?
3. Ask what information was available at declaration time versus only
   became visible later -- if the information needed to classify
   correctly *was* available (e.g. a cross-service dependency graph
   showing the blast radius) but wasn't consulted, that's a process gap,
   not bad luck.
4. Check whether severity was ever revisited during the incident, or
   whether it was set once and never re-evaluated despite worsening
   signals.

## Fix
Define severity levels by concrete, checkable thresholds (revenue impact
per minute, percentage of requests failing, which specific
customer-facing flows are broken, SLO burn-rate) rather than subjective
adjectives, so classification doesn't depend on one person's judgment or
risk appetite. Bias the initial classification toward the higher severity
when impact is uncertain -- it's cheaper to de-escalate a Sev1 that
turned out contained than to escalate a Sev3 that turned out to be
company-wide, so make de-escalation procedurally easy and normal rather
than embarrassing. Build in a mandatory re-evaluation checkpoint (e.g. at
15 minutes if not resolved) that explicitly asks "has the blast radius
changed" rather than leaving severity static until someone happens to
notice it's wrong. Make the escalation path from any severity level to
paging additional specialists or leadership a single low-friction action
(one command/button), not a judgment call requiring justification.

## Pitfalls
Don't fix this by making everyone declare Sev1 by default "to be safe" --
that just recreates alert fatigue at the incident-severity level and
leadership stops treating Sev1 pages as urgent. The threshold-based
rubric must be genuinely calibrated to reserve top severity for what
actually needs top-severity response. Also don't punish or call out the
person who under-classified initially in the postmortem -- if
de-escalating/re-escalating carries social cost, people will keep
under-classifying to avoid being wrong publicly, which defeats the fix.

## Verify
After introducing the concrete rubric and re-evaluation checkpoint, check
the next several incidents' timelines for the gap between impact-start
and right-people-engaged -- it should shrink measurably. Also audit a
sample of Sev1/Sev2 declarations for whether they matched the objective
thresholds (not just gut feel), confirming the rubric is actually being
used rather than bypassed.
