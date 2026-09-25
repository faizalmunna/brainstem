---
name: postmortem-root-cause-stops-at-trigger
description: A postmortem's root cause section names the immediate trigger, like a bad deploy, without explaining why the process let that trigger cause an outage.
triggers: ["postmortem root cause is too shallow", "root cause just says bad deploy", "why did this get past our safeguards", "five whys postmortem", "postmortem doesn't explain systemic issue"]
permissions: ["READ"]
---

## Symptom
A postmortem document lists a "root cause" that is really just the
proximate trigger -- "a bad deploy introduced a null pointer exception,"
"an engineer ran the wrong migration," "a config value was set
incorrectly." The document is internally consistent and factually
accurate, but reading it gives no insight into why the organization's
safeguards (review, tests, gradual rollout, alerting) failed to catch or
contain something this ordinary before it became a customer-facing
outage. The same *category* of trigger (a bad deploy, a fat-fingered
config change) recurs in later incidents because nothing about the
system that let it through actually changed.

## Likely causes
- **The postmortem template stops at "what broke" instead of asking "why
  did our defenses not catch this"** -- there's a root-cause field but no
  structured prompt to keep asking why past the first plausible answer.
- **Whoever wrote it was also the person who made the mistake**, and
  there's unconscious (or conscious) pressure to close the narrative
  quickly at "I made an error" rather than surface that no one was
  required to review the change, or that staged rollout wasn't used.
- **Time pressure to close the postmortem** treats a named trigger as
  "done" because it's concrete and satisfies the ticket, even though a
  trigger without a systemic explanation guarantees recurrence.
- **No one owns pushing back on shallow postmortems** -- there's no
  review step (a postmortem reviewer, an incident review meeting) that
  asks "why wasn't this caught earlier," so shallow ones ship unchallenged.

## Diagnose
1. Read the root cause section and ask: "if this exact trigger happened
   again tomorrow, would anything actually stop it?" If the honest answer
   is no, the postmortem stopped too early.
2. Apply five-whys explicitly against the document: for the stated
   trigger, ask "why did this reach production" repeatedly until you hit
   a process/system answer (no canary stage, no required reviewer for
   this code path, no automated test for this class of bug, no
   feature-flag kill switch) rather than a human-error answer.
3. Check whether the incident's category (bad deploy, bad config, bad
   migration) appears in prior postmortems. Search the postmortem
   archive/index for the same trigger type -- recurrence across separate
   incidents is direct evidence the systemic cause was never fixed.
4. Check whether the action items address the trigger (e.g. "fix the null
   check") or the systemic gap (e.g. "require staged rollout for this
   service," "add a pre-deploy check for this class of error"). Trigger-
   only action items are the tell.

## Fix
Restructure the root-cause analysis to require at least one "why did our
process allow this" answer, not just "what technically happened."
Concretely: after naming the trigger, add a mandatory second section --
"contributing systemic factors" -- that must name at least one gap in
review, testing, deployment safety (canary/staged rollout, automated
rollback), or alerting that let the trigger reach users. Action items
should target that systemic gap (add a gate, add a test category, add a
kill switch) rather than only the specific line of code or specific
person's mistake. This generalizes because the actual value of a
postmortem isn't documenting one incident -- it's removing a whole class
of future incidents, which requires naming the mechanism that let this
class through in the first place.

## Pitfalls
Don't overcorrect into blaming "the process" so abstractly that no
concrete action item results ("we need a culture of quality" is not
actionable). The systemic factor must be specific and fixable -- name the
exact missing gate, not a vague value statement. Also don't let "five
whys" turn into re-litigating unrelated organizational issues far removed
from this incident; stop at the first systemic cause that, if fixed,
would have prevented or contained this specific incident.

## Verify
Re-read the finished postmortem and confirm a reader who wasn't there
could answer "what specifically will prevent this category of trigger
from reaching production again" from the document alone, and that at
least one action item is a process/system change (not just a code fix)
with an owner and a due date. Track the trigger category going forward:
if the same category resurfaces after the fix ships, the systemic cause
wasn't actually the one identified.
