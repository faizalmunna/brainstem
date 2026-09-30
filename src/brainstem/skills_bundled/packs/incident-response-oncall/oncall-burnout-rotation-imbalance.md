---
name: oncall-burnout-rotation-imbalance
description: On-call responders are burning out because page volume or rotation frequency is unevenly distributed and never measured, degrading incident response quality.
triggers: ["on-call is burning people out", "same person always gets paged", "on-call rotation is unfair", "engineers dreading on-call week", "on-call attrition"]
permissions: ["READ"]
---

## Symptom
Engineers on a team are increasingly reluctant to take on-call shifts,
some quietly avoid volunteering while others end up covering
disproportionately more weeks, and response quality visibly degrades
during certain people's shifts -- slower acknowledgment, more mistakes
under fatigue, occasional missed pages -- in a pattern that tracks
individual burnout rather than random chance. Left unaddressed, this
shows up as attrition (people leaving the team or the company citing
on-call load) or as a growing informal blacklist of who's willing to be
on the rotation at all.

## Likely causes
- **Page volume/severity isn't distributed evenly across the rotation**
  -- if certain shifts (weekends, specific time zones, specific service
  ownership) reliably get paged far more than others, a rotation that
  looks fair on a calendar is unfair in actual load.
- **The rotation includes people without the context/authority to
  resolve common pages**, so their shifts involve more escalation, more
  waking up a second person, and more stress than someone who can
  actually fix things solo.
- **No one is tracking page volume, after-hours pages, or shift-level
  outcomes over time**, so the imbalance is invisible until someone
  burns out visibly enough to complain or quit -- there's no early
  metric acting as a leading indicator.
- **Underlying noisy alerts (see alert fatigue) inflate on-call load
  independent of rotation fairness** -- even a perfectly even rotation
  produces burnout if the absolute page volume per shift is too high to
  begin with.
- **Compensation or time-off-in-lieu for on-call burden doesn't exist or
  doesn't scale with actual load**, so the personal cost of a bad week is
  entirely uncompensated, which erodes goodwill toward the rotation over
  time regardless of fairness.

## Diagnose
1. Pull per-shift page counts (total and after-hours/night-time
   specifically) for the last several rotation cycles, broken out by
   individual -- look for outliers, not just averages, since a fair
   average can hide a few people absorbing most of the pain.
2. Check whether page volume correlates with specific days/times
   (weekends, a particular region's business hours) that some rotation
   slots always land on due to how the schedule is built, rather than
   being randomly distributed across the team.
3. Look at acknowledgment time and resolution quality (reopened
   incidents, escalations to a second person) segmented by which
   individual was on call -- a consistent pattern for one person across
   multiple shifts points to either an unfair load or a support gap
   (missing context/access), not an individual competence issue.
4. Ask the rotation directly (a short anonymous survey is enough) whether
   people feel the load is fair and sustainable -- self-report catches
   dissatisfaction before it shows up in attrition data.

## Fix
Track page volume and after-hours pages per person per rotation cycle as
an ongoing metric, not just a one-time audit, and use it to actively
rebalance the schedule (rotate who gets weekend/night slots, adjust shift
length, or add more people to the rotation) rather than leaving the
schedule static indefinitely. Separately attack the absolute volume via
the alert-quality work (tuning noisy alerts down) since rebalancing a
too-high total load only redistributes pain rather than reducing it.
Ensure everyone in the rotation has the access/context/runbooks needed to
resolve the common page types solo, so on-call load isn't secretly
concentrated on whoever happens to have tribal knowledge. Where
sustainable, provide explicit compensation or time-off-in-lieu tied to
actual on-call burden (especially after-hours pages), so the cost isn't
purely absorbed as unrecognized personal sacrifice.

## Pitfalls
Don't respond to a burnout complaint by just adding more people to the
rotation without checking whether they have the context to actually
resolve pages -- diluting the schedule with under-equipped responders
can worsen mean-time-to-resolution even as it reduces any one person's
shift frequency. Also don't treat a single bad week as proof of systemic
imbalance without checking the trend across several cycles -- some
variance is normal, and overreacting to one noisy week can produce
unnecessary rotation churn.

## Verify
After rebalancing, confirm the per-person page-count and after-hours-page
distribution across the next several rotation cycles is materially more
even than the historical baseline, not just for the cycle immediately
following the change. Re-run the sustainability survey after one to two
quarters and check for improvement in self-reported fairness/sustainability,
alongside a check that on-call-attributed attrition or rotation opt-outs
have decreased.
