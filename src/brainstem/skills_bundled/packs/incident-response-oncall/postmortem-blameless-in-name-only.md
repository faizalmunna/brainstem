---
name: postmortem-blameless-in-name-only
description: A team claims blameless postmortem culture as a value but the actual document reads as blaming a specific individual, undermining psychological safety.
triggers: ["postmortem blames a person", "blameless postmortem doesn't feel blameless", "postmortem names who caused the outage", "people are afraid to admit mistakes in postmortems", "engineer got blamed for the outage"]
permissions: ["READ"]
---

## Symptom
The team's stated process says postmortems are "blameless," but the
actual document names a specific engineer ("Alice deployed without
running the test suite," "Bob approved the PR that caused this") in a
way that reads as fault-finding, action items are phrased as things that
individual should do differently ("Alice should be more careful"), and
afterward, people are visibly more reluctant to volunteer that they were
involved in the next incident, or postmortem narratives start getting
vaguer and less honest about what actually happened.

## Likely causes
- **The postmortem template asks "who did X" instead of "what
  happened,"** which naturally produces individual-attribution language
  even when the author didn't intend to assign blame.
- **The author (often the person involved, or their manager) doesn't
  distinguish between narrating a fact (a specific person ran a specific
  command) and implying fault** -- factual specificity reads as blame
  when it's not paired with "and here's why the system let that be
  possible."
- **Leadership references the postmortem in performance conversations**
  (even once, even informally), which teaches everyone that postmortem
  content has consequences for individuals, so future postmortems either
  get sanitized/vague or people avoid volunteering details.
- **No one reviews postmortems for tone/framing before publishing** --
  there's a technical review for accuracy but nothing checks whether the
  document would feel safe to the people named in it.

## Diagnose
1. Read the document and mechanically count sentences with a named
   individual as the subject of a mistake ("X did Y wrong") versus
   sentences with a system/process as the subject ("the deploy pipeline
   allowed Y to happen without a review gate"). A high ratio of the
   former is the direct signature.
2. Check the action items specifically: do any of them read as "person X
   will be more careful/thorough" rather than "the system will add a
   check/gate/test"? Individual-behavior-change action items are close to
   always a sign the analysis stopped at blame instead of reaching a
   systemic fix.
3. Ask the person named in a past postmortem, privately, how it felt to
   read -- direct signal is more reliable than inferring intent from the
   text alone.
4. Look for a trend across recent postmortems: are they getting vaguer or
   shorter over time, or are fewer people volunteering to author them?
   That's evidence the culture has already adapted defensively to a
   non-blameless reality.

## Fix
Rewrite postmortem narrative to describe actions in terms of what the
system/process made possible, not what a person is like: "a deploy
without an automated pre-flight check reached production" rather than
"Alice didn't check before deploying" -- both are factually about the
same event, but only the first is also an analysis of what to fix. Where
a specific person's action is relevant to the timeline, state it neutrally
as a fact needed for reconstruction, and immediately follow it with the
systemic question ("and why was that action possible/likely, and what
would prevent it structurally"). Make it an explicit, enforced norm --
possibly a checklist item during postmortem review -- that leadership
never references named individuals from a postmortem in a performance or
disciplinary context; if that norm is ever broken even once, treat it as
a serious trust failure to repair explicitly, not something to quietly
move past.

## Pitfalls
Don't over-correct into scrubbing all specificity from the timeline in
the name of blamelessness -- a postmortem that's vague about what
actually happened ("a change was made that had unintended effects") loses
the diagnostic value needed to fix the systemic cause. Blameless means
not punishing the individual, not omitting facts. Also don't assume
intent alone fixes this -- a team can sincerely believe it's blameless
while its documents and follow-up conversations still produce blame in
effect; culture is demonstrated by what the artifacts and consequences
actually look like, not by the stated value.

## Verify
Have someone not involved in the incident read the finished postmortem
and identify who (if anyone) they'd feel was "at fault" -- if they can
name a specific individual as the takeaway, the document isn't blameless
regardless of the label on the template. Track postmortem participation
and narrative detail over several incidents; a working blameless culture
shows people continuing to volunteer specific, honest detail about their
own involvement rather than authorship and detail shrinking over time.
