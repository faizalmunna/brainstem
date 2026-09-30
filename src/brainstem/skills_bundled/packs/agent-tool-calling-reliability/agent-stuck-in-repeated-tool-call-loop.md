---
name: agent-stuck-in-repeated-tool-call-loop
description: An agent repeatedly calls the same tool with identical or trivially varied arguments across many turns without making progress toward the goal.
triggers: ["agent stuck in a loop", "same tool called over and over", "agent not making progress", "infinite tool calling loop", "burning tokens calling the same function"]
permissions: ["READ"]
---

## Symptom
The agent's transcript shows the same tool invoked many turns in a row --
sometimes with byte-identical arguments, sometimes with cosmetic
variations (retrying a search with a slightly reworded query, re-reading
the same file) -- while the task state never advances. The run either
times out, exhausts a token/cost budget, or is killed manually.

## Likely causes
1. **The tool's result doesn't give the model new information it can act
   on** -- e.g. a search tool returns the same top results every time, or
   an error message is too generic ("failed") for the model to form a
   different next action, so it tries essentially the same thing again.
2. **No loop/repetition detection in the agent harness** -- nothing is
   comparing the current tool call against recent history, so there's no
   mechanism to interrupt the pattern even after many repeats.
3. **The task genuinely requires information or a capability the agent
   doesn't have** (a missing tool, an unreachable resource, a
   permission the agent lacks) and instead of concluding "I cannot do
   this," the model keeps trying variations of the only lever it has.
4. **Conflicting or ambiguous instructions in the system prompt** push the
   model toward re-attempting a step it already believes it completed,
   because a later instruction re-triggers the same sub-goal.
5. **Stateless tool wrapping a stateful process** -- e.g. a "run tests"
   tool that doesn't surface that a previous run already fixed the
   issue, so the model can't tell progress was made and re-runs the same
   diagnostic instead of moving forward.

## Diagnose
- Extract the sequence of (tool_name, arguments) pairs from the
  transcript and compute exact or near-duplicate matches (normalize
  whitespace/casing) across a sliding window -- quantify how many of the
  last N calls are repeats before assuming it's a "loop" versus
  legitimate iterative refinement.
- Inspect the tool *results* the model received right before each repeat
  -- if the result text is generic or truncated, the model may be
  repeating because it genuinely can't extract a next step from it.
- Check whether the model's own reasoning/scratchpad text (if captured)
  says something like "let me try again" or restates the same plan --
  this indicates it believes it's making progress when it isn't, versus
  cases where it explicitly says it's stuck (a sign the harness should
  have intervened already).
- Confirm whether a required tool for completing the task actually exists
  in the registry -- a loop is sometimes the model correctly recognizing
  it needs capability X and repeatedly trying the closest available tool
  because X was never provided.

## Fix
Add an explicit repetition guard in the agent harness, not in the prompt
alone (prompted instructions like "don't repeat yourself" are
unreliable under pressure). Track a rolling hash of (tool_name,
normalized_arguments) for the last N calls; when the same signature
repeats past a threshold (e.g. 3 times), don't just keep calling the
model -- inject a synthetic system/tool message that surfaces the
repetition explicitly ("You have called X with these same arguments 3
times without new results; the last result was: ... Consider a
different approach or report that you're blocked") and force a
reasoning step before allowing another tool call. Pair this with making
tool error/result messages information-dense enough to actually change
the model's next decision (state what was tried, what's still missing,
and what alternatives exist) rather than a bare failure string. For
cases where the loop stems from a genuinely missing capability, give the
model an explicit "report blocked / request escalation" action as a
first-class tool so it has somewhere to go besides repeating itself.

## Pitfalls
- Setting the repetition threshold too low and killing legitimate
  iterative work (e.g. a linter-fix-relint cycle that takes 4-5 rounds to
  converge) -- tune the threshold and the similarity check per tool
  category rather than one global constant.
- Hard-killing the run the moment a loop is detected instead of first
  trying a corrective nudge -- many loops resolve after a single explicit
  "you're repeating yourself" message, so terminate only after the nudge
  also fails.
- Comparing tool calls with exact string equality only, missing
  near-duplicate loops (same search reworded, same file path with a
  trailing slash) -- normalize and consider semantic similarity for
  read/search-style tools specifically.

## Verify
Replay a transcript known to loop (or synthetically force a tool to
return the same unhelpful result repeatedly) through the harness with
the repetition guard enabled, and confirm the run exits the loop within
the configured threshold -- either by producing a materially different
next action or by surfacing an explicit "blocked" outcome -- instead of
running until an external timeout or budget cap kills it.
