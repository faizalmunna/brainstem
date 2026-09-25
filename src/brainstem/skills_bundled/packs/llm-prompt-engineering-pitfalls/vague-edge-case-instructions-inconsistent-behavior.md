---
name: vague-edge-case-instructions-inconsistent-behavior
description: The system prompt is silent or vague about ambiguous edge-case inputs, so the model's behavior on those inputs varies inconsistently from run to run.
triggers: ["model gives different answers to the same edge case", "inconsistent behavior on ambiguous input", "model sometimes refuses sometimes answers the same question", "flaky behavior only on unusual inputs"]
permissions: ["READ"]
---

## Symptom
For the common, well-specified case, the model behaves consistently. But for a specific category of ambiguous or edge-case input (an empty field, a request that's borderline out-of-scope, conflicting user-provided data), the same or similar input produces different behavior across runs -- sometimes answering, sometimes refusing, sometimes picking one of several plausible interpretations -- without any change in the input itself, only sampling variance deciding which path the model takes.

## Likely causes
1. **The prompt never actually specifies what should happen for this input category** -- it was written to cover the main task, and the edge case simply wasn't considered, so the model is making up a reasonable-sounding policy on the fly each time, and "reasonable-sounding" varies with sampling.
2. **The instructions are contradictory rather than merely silent** -- one part of the prompt implies one behavior for ambiguous input (e.g. "always provide an answer") while another part implies the opposite (e.g. "if unsure, ask for clarification"), and which one "wins" varies by run.
3. **Non-zero temperature amplifies an underspecified decision boundary** -- when the model's implicit confidence between two interpretations is close, small sampling differences tip the choice one way or the other, which wouldn't be visible if the boundary were clearly specified and confidence were lopsided.
4. **The edge case is genuinely rare in whatever data or examples shaped the model's behavior for this task**, so the model has weak, high-variance priors for it specifically, compared to strong, consistent priors for the common case.
5. **The definition of "edge case" itself is fuzzy to the team**, so nobody has actually enumerated what the ambiguous input categories even are, making it hard to address systematically rather than one complaint at a time.

## Diagnose
- Run the same ambiguous input multiple times (5-10 repetitions) at the production temperature setting and record the distribution of behaviors -- this confirms it's genuine run-to-run inconsistency rather than a single reproducible bug.
- Search the prompt for any instruction that touches this input category at all -- if none exists, that confirms silence; if multiple instructions touch it with different implications, that confirms contradiction rather than mere silence.
- Re-run the same input at temperature 0 (or the lowest available) -- if behavior becomes consistent (even if it's consistently the "wrong" choice), that confirms sampling variance around an underspecified decision boundary rather than a deeper misunderstanding of the task.
- Enumerate all edge-case categories the team can think of by reviewing a sample of real inputs and flagging anything that doesn't cleanly fit the prompt's explicit specification.

## Fix
Explicitly enumerate the ambiguous cases in the prompt and state the intended policy for each -- not just "handle edge cases sensibly," but a concrete rule (e.g. "if the user's request could mean X or Y and there's no way to tell, ask a single clarifying question rather than guessing" or "if the field is empty, treat it as N/A and proceed"). Where genuinely irreducible ambiguity remains, decide and state a deterministic tie-breaking rule rather than leaving it to sampling, since a consistent, documented default is more debuggable and more trustworthy to users than a coin-flip that occasionally goes either way. Resolve any contradictions found between different parts of the prompt (e.g. a global "always answer" instruction versus a task-specific "ask for clarification" instruction) by making the precedence explicit.

## Pitfalls
Adding an edge case to the prompt only after a user complains, one at a time, without ever doing the enumeration exercise, means the prompt accumulates ad hoc patches while the underlying pattern -- vague handling of anything not in the happy path -- remains unaddressed for the next edge case that hasn't been hit yet.

## Verify
Re-run the specific ambiguous input(s) 10+ times at the production temperature after the fix and confirm the model's behavior is now consistent (same interpretation or the same clarifying-question pattern every time), then check the fix against the full enumerated edge-case list from Diagnose, not just the one case that originally prompted the investigation.
